"""A real app server over fake services: a scripted model stream, fake kernels, a temporary workspace."""

import time
from types import SimpleNamespace

import httpx
import pytest
from starlette.testclient import TestClient

from sillytherin import config, llm, turn
from sillytherin.server import app as server_app
from sillytherin.server.app import ServerSettings, create_app
from sillytherin.server.socket import ChatSessions
from sillytherin.workspace import actions
from sillytherin.workspace.datasets.service import DatasetService, DatasetsSettings
from sillytherin.workspace.kaggle.account import KaggleAccountService
from sillytherin.workspace.kaggle.token_file import TokenFile
from sillytherin.workspace.panel import PanelRegistry
from sillytherin.workspace.service import NotebookService
from tests.kaggle.fakes import FakeListener
from tests.scripted_chat_model import (  # noqa: F401 - shared with the socket tests
    HANG,
    ScriptedChatModel,
    text_chunk,
    tool_call_chunk,
)

PORT = 8000
OWN_HOST = f"127.0.0.1:{PORT}"
OWN_PAGE = f"http://{OWN_HOST}"
@pytest.fixture
def model(monkeypatch) -> ScriptedChatModel:
    scripted = ScriptedChatModel()
    monkeypatch.setattr(turn, "build_chat_model", lambda _request: scripted)
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
