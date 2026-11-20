"""A real app server over fake services: a scripted model stream, fake kernels, a temporary workspace."""

import asyncio
import json
import time
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Self

import httpx
import pytest
from starlette.testclient import TestClient

from researchchat import config, llm
from researchchat.server import app as server_app
from researchchat.server.app import ServerSettings, create_app
from researchchat.server.socket import ChatSessions
from researchchat.workspace import actions
from researchchat.workspace.datasets.service import DatasetService, DatasetsSettings
from researchchat.workspace.kaggle.account import KaggleAccountService
from researchchat.workspace.kaggle.token_file import TokenFile
from researchchat.workspace.panel import PanelRegistry
from researchchat.workspace.service import NotebookService
from tests.kaggle.fakes import FakeListener

PORT = 8000
OWN_HOST = f"127.0.0.1:{PORT}"
OWN_PAGE = f"http://{OWN_HOST}"
HANG = object()  # in a script: the stream waits here until the turn is stopped


def text_chunk(text: str) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text, reasoning=None, tool_calls=None))])


def tool_call_chunk(name: str, arguments: dict, call_id: str = "call-1") -> SimpleNamespace:
    call = SimpleNamespace(index=0, id=call_id, function=SimpleNamespace(name=name, arguments=json.dumps(arguments)))
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None, reasoning=None, tool_calls=[call]))])


class ScriptedStream:
    def __init__(self, chunks: list) -> None:
        self.chunks = chunks

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        pass

    def __aiter__(self):
        return self._chunks()

    async def _chunks(self):
        for chunk in self.chunks:
            if chunk is HANG:
                await asyncio.Event().wait()
            yield chunk


@dataclass
class ScriptedModel:
    """Answers each model call with the next script; "ok" once the scripts run out. Remembers every request."""

    scripts: list[list] = field(default_factory=list)
    requests: list[dict] = field(default_factory=list)

    async def create(self, **request: object) -> ScriptedStream:
        self.requests.append(request)
        return ScriptedStream(self.scripts.pop(0) if self.scripts else [text_chunk("ok")])

    def tool_names(self, request_index: int) -> list[str]:
        return [tool["function"]["name"] for tool in self.requests[request_index].get("tools", [])]


@pytest.fixture
def model(monkeypatch) -> ScriptedModel:
    scripted = ScriptedModel()
    monkeypatch.setattr(llm, "client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=scripted.create))))
    catalog = {config.MODEL: llm.ModelInfo(id=config.MODEL, name="Test model", params=frozenset({"tools", "reasoning"}))}
    monkeypatch.setattr(llm, "_catalog", catalog)
    return scripted


@pytest.fixture
def services(tmp_path, fake_kernels, monkeypatch) -> SimpleNamespace:
    """The app's services as actions.py wires them, over a temporary workspace and fake kernels."""
    root = tmp_path / "workspaces"
    panels = PanelRegistry()
    chats = actions.ChatRegistry()
    notebook = NotebookService(fake_kernels, root=root, notify=panels.push)
    datasets = DatasetService(
        settings=DatasetsSettings(min_free_disk_mb=0, ask_above_mb=200, max_files=500, parallel_downloads=0, stall_timeout_seconds=1),
        root=root, props=notebook.props, notify=panels.push, send=chats.send,
    )
    notebook.datasets = datasets.panel_state
    notebook.after_run = datasets.sync_created
    datasets.created.run_lock = notebook.run_lock
    kaggle = KaggleAccountService(
        token_file=TokenFile(tmp_path / "kaggle.json"), http_factory=lambda: httpx.AsyncClient(),
        listener_factory=FakeListener, signin_timeout_seconds=1, now=time.monotonic,
        on_change=actions.refresh_kaggle_switch_everywhere,
    )
    for name, value in (("panels", panels), ("chats", chats), ("service", notebook), ("datasets", datasets),
                        ("kernels", fake_kernels), ("kaggle_account", kaggle)):
        monkeypatch.setattr(actions, name, value)

    async def nothing() -> None:
        pass

    monkeypatch.setattr(server_app, "run_startup_cleanup", nothing)
    monkeypatch.setattr(server_app, "stop_kernels", nothing)
    return SimpleNamespace(root=root, panels=panels, chats=chats, notebook=notebook, kernels=fake_kernels)


@pytest.fixture
def sessions() -> ChatSessions:
    return ChatSessions(grace_seconds=0.2)


@pytest.fixture
def client(services, model, sessions, tmp_path):
    app = create_app(ServerSettings(port=PORT, page_dir=tmp_path / "page"), sessions)
    with TestClient(app, base_url=OWN_PAGE) as test_client:
        yield test_client


def open_tab(client: TestClient, chat_id: str | None = None):
    """A socket from the app's own page; use it as a context manager."""
    path = "/ws/chat" if chat_id is None else f"/ws/chat?chat_id={chat_id}"
    return client.websocket_connect(path, headers={"origin": OWN_PAGE, "host": OWN_HOST})


def events_until(socket, event_type: str, limit: int = 200) -> list[dict]:
    """Every event up to and including the first of `event_type`."""
    events = []
    for _ in range(limit):
        event = socket.receive_json()
        events.append(event)
        if event["type"] == event_type:
            return events
    raise AssertionError(f"no {event_type} in {[e['type'] for e in events]}")


def send_message(socket, text: str = "hi") -> None:
    socket.send_json({"type": "chat.send", "text": text, "model": config.MODEL, "effort": "default"})


def next_event_after_probe(socket) -> dict:
    """Send an answer no prompt has, so the next event shows whether anything else arrived before it."""
    socket.send_json({"type": "ask.answer", "ask_id": "probe", "choice": "run"})
    return socket.receive_json()
