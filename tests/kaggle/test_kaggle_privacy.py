"""The Kaggle tokens never show up anywhere the user, the assistant or notebook code can see."""

import asyncio
import logging
import re
import urllib.parse
from dataclasses import asdict
from pathlib import Path

from sillytherin.config import KAGGLE_TOKEN_FILE, WORKSPACES_DIR
from sillytherin.workspace.kaggle.callback import CallbackListener, CallbackResult
from sillytherin.workspace.kaggle.my_datasets import LIST_DATASETS_URL
from sillytherin.workspace.kaggle.settings_switch import (
    apply_account_change,
    kaggle_switch,
)
from tests.kaggle.fakes import (
    ACCESS_TOKEN,
    REFRESH_TOKEN,
    REFRESHED_ACCESS_TOKEN,
    FakeKaggle,
    answer,
)
from tests.kaggle.test_kaggle_account import Harness
from tests.kaggle.test_kaggle_settings_switch import FakeChat, settle

TOKENS = (ACCESS_TOKEN, REFRESHED_ACCESS_TOKEN, REFRESH_TOKEN)
KAGGLE_SOURCES = Path(__file__).resolve().parents[2] / "sillytherin" / "workspace" / "kaggle"
ALLOWED_KAGGLE_URLS = {
    "https://www.kaggle.com/api/v1/oauth2/authorize",
    "https://www.kaggle.com/api/v1/oauth2/token",
    "https://www.kaggle.com/api/v1/oauth2/register",
    "https://api.kaggle.com/v1/users.AccountService/ExpireApiToken",
    LIST_DATASETS_URL,
}


def run(coro):
    return asyncio.run(coro)


def everything_shown(h: Harness, chat: FakeChat) -> str:
    """All text the chat and Settings showed during the flow."""
    shown = [message for message, _kind in chat.toasts]
    shown += chat.popup.shown + [message for _state, message in chat.popup.finished]
    shown += [repr(asdict(kaggle_switch(status))) for status in h.changes]
    shown += [repr(status) for status in h.changes]
    return "\n".join(shown)


async def connect_refresh_disconnect(h: Harness, chat: FakeChat) -> None:
    await apply_account_change("connect", h.service, chat.side())
    h.listener.come_back(CallbackResult("code", "approval-code-1"))
    await h.service.wait_for_sign_in()
    await settle()
    h.clock.seconds += 4 * 60 * 60
    await h.service.access_token()
    await apply_account_change("disconnect", h.service, chat.side())


# Baseline: Given a connected account whose tokens are distinctive strings · When connect, refresh and disconnect run with logging at DEBUG


def test_tokens_not_in_settings_or_chat(tmp_path) -> None:
    # Changed: capture every switch, toast, chat message and pop-up prop · Then: neither token appears · Demonstrates: chat and Settings stay clean
    h, chat = Harness(tmp_path), FakeChat()
    run(connect_refresh_disconnect(h, chat))
    shown = everything_shown(h, chat)
    assert "Kaggle connected as ana" in shown  # the flow really ran
    for token in TOKENS:
        assert token not in shown


def test_tokens_not_in_logs(tmp_path, caplog) -> None:
    # Changed: all log records · Then: neither token appears · Demonstrates: logs stay clean
    caplog.set_level(logging.DEBUG)
    h, chat = Harness(tmp_path), FakeChat()
    run(connect_refresh_disconnect(h, chat))
    logged = caplog.text + "\n".join(repr(record.args) for record in caplog.records)
    for token in TOKENS:
        assert token not in logged


def test_tokens_not_under_workspaces(tmp_path) -> None:
    # Changed: scan every file under a tmp workspaces folder · Then: neither token appears; the sign-in file is outside it · Demonstrates: no project folder holds the token
    workspaces = tmp_path / "workspaces"
    (workspaces / "default" / "files").mkdir(parents=True)
    h = Harness(tmp_path / "config")
    run(h.connect_and_come_back(CallbackResult("code", "approval-code-1")))
    run(h.service.access_token())
    for path in workspaces.rglob("*"):
        if path.is_file():
            assert not any(token.encode() in path.read_bytes() for token in TOKENS)
    assert workspaces not in h.file.path.parents
    assert WORKSPACES_DIR.resolve() not in KAGGLE_TOKEN_FILE.resolve().parents


def test_callback_code_not_logged(caplog) -> None:
    # Changed: a callback carrying a distinctive code · Then: the code is not logged · Demonstrates: the one-time code stays private
    caplog.set_level(logging.DEBUG)

    async def browser_comes_back() -> CallbackResult:
        listener = CallbackListener("state-1", timeout_seconds=5)
        redirect = await listener.start()
        waiting = asyncio.create_task(listener.wait())
        port = urllib.parse.urlsplit(redirect).port
        reader, writer = await asyncio.open_connection("127.0.0.1", port)  # a raw request, like a browser's
        writer.write(b"GET /callback?code=CODE-SECRET-42&state=state-1 HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()
        await reader.read()
        writer.close()
        return await waiting

    result = run(browser_comes_back())
    assert result.code == "CODE-SECRET-42"
    assert "CODE-SECRET-42" not in caplog.text
    assert "CODE-SECRET-42" not in repr(result)


def test_errors_do_not_echo_kaggle_body(tmp_path) -> None:
    # Changed: Kaggle answers 400 with a body that contains the token · Then: no toast, description or exception text contains it · Demonstrates: fixed messages only
    leaky = answer(400, {"error": "invalid_request", "error_description": f"bad token {REFRESH_TOKEN}"})
    h, chat = Harness(tmp_path, kaggle=FakeKaggle(token=leaky)), FakeChat()

    async def scenario() -> None:
        await apply_account_change("connect", h.service, chat.side())
        h.listener.come_back(CallbackResult("code", "approval-code-1"))
        await h.service.wait_for_sign_in()
        await settle()

    run(scenario())
    shown = everything_shown(h, chat) + repr(h.service.status())
    assert "Couldn't connect to Kaggle" in shown
    assert REFRESH_TOKEN not in shown


def test_account_code_calls_no_write_endpoints() -> None:
    # Changed: read the Kaggle account sources · Then: only the sign-in, token, register and revoke endpoints appear · Demonstrates: the full-account scope is only used to read
    urls = set()
    for source in KAGGLE_SOURCES.glob("*.py"):
        urls |= set(re.findall(r"https://[A-Za-z0-9./_-]+", source.read_text()))
    assert urls == ALLOWED_KAGGLE_URLS
