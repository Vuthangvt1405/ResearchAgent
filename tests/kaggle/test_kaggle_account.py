"""Connecting, disconnecting and access tokens for downloads."""

import asyncio
import json

import pytest

from researchchat.workspace import ErrorCode, WorkspaceError
from researchchat.workspace.kaggle import oauth
from researchchat.workspace.kaggle.account import (
    CANCELLED_NOTICE,
    REFUSED_NOTICE,
    REVOKE_UNREACHABLE_NOTICE,
    SIGNED_OUT_NOTICE,
    TIMED_OUT_NOTICE,
    KaggleAccountService,
    KaggleAccountStatus,
)
from researchchat.workspace.kaggle.callback import CallbackResult
from researchchat.workspace.kaggle.token_file import SavedSignIn, TokenFile
from tests.kaggle.fakes import (
    CLIENT_ID,
    REFRESH_TOKEN,
    REFRESHED_ACCESS_TOKEN,
    USERNAME,
    FakeKaggle,
    FakeListener,
    answer,
    network_down,
)

SAVED = SavedSignIn(client_id=CLIENT_ID, refresh_token=REFRESH_TOKEN, username=USERNAME, connected_at="2026-11-19T10:00:00Z")
THREE_HOURS = 3 * 60 * 60


def run(coro):
    return asyncio.run(coro)


class Clock:
    def __init__(self) -> None:
        self.seconds = 1000.0

    def __call__(self) -> float:
        return self.seconds


class Harness:
    """One account service wired to a mock Kaggle, a fake listener, a fake clock and a tmp sign-in file."""

    def __init__(self, tmp_path, kaggle: FakeKaggle | None = None, saved: SavedSignIn | None = None):
        FakeListener.created.clear()
        self.kaggle = kaggle or FakeKaggle()
        self.file = TokenFile(tmp_path / "kaggle-account.json")
        if saved:
            self.file.save(saved)
        self.clock = Clock()
        self.changes: list[KaggleAccountStatus] = []
        self.service = KaggleAccountService(
            token_file=self.file,
            http_factory=self.kaggle.client,
            listener_factory=FakeListener,
            signin_timeout_seconds=600,
            now=self.clock,
            on_change=self._record,
        )

    async def _record(self, status: KaggleAccountStatus) -> None:
        self.changes.append(status)

    @property
    def listener(self) -> FakeListener:
        return FakeListener.created[-1]

    async def connect_and_come_back(self, result: CallbackResult) -> str | None:
        url = await self.service.start_connect()
        self.listener.come_back(result)
        await self.service.wait_for_sign_in()
        return url


APPROVED = CallbackResult("code", "approval-code-1")


# Baseline: Given no sign-in file, a mock Kaggle and a fake listener whose callback the test triggers · When connecting and then the callback brings a code


def test_connect_saves_sign_in_and_reports_username(tmp_path) -> None:
    # Changed: — · Then: the file holds client id, refresh token and username; status is connected as that user; the change is announced · Demonstrates: connecting
    h = Harness(tmp_path)
    run(h.connect_and_come_back(APPROVED))
    saved = h.file.load()
    assert (saved.client_id, saved.refresh_token, saved.username) == (CLIENT_ID, REFRESH_TOKEN, USERNAME)
    assert h.service.status() == KaggleAccountStatus("connected", username=USERNAME)
    assert h.changes[-1] == KaggleAccountStatus("connected", username=USERNAME)


def test_connect_registers_with_listener_port(tmp_path) -> None:
    # Changed: — · Then: the registered redirect and the authorize URL both use the listener's address · Demonstrates: Kaggle sends the user back to the right port
    h = Harness(tmp_path)
    url = run(h.connect_and_come_back(APPROVED))
    listener_uri = f"http://127.0.0.1:{FakeListener.PORT}/callback"
    registered = json.loads(h.kaggle.calls_to(oauth.REGISTER_URL)[0].content)
    assert registered["redirect_uris"] == [listener_uri]
    assert f"redirect_uri={listener_uri.replace(':', '%3A').replace('/', '%2F')}" in url
    assert f"state={h.listener.expected_state}" in url


def test_connect_while_connecting_replaces_old_flow(tmp_path) -> None:
    # Changed: connect twice · Then: the first listener is closed and only the second state counts · Demonstrates: turning on twice is safe
    h = Harness(tmp_path)

    async def scenario():
        first_url = await h.service.start_connect()
        first = h.listener
        second_url = await h.service.start_connect()
        second = h.listener
        second.come_back(APPROVED)
        await h.service.wait_for_sign_in()
        return first, second, first_url, second_url

    first, second, first_url, second_url = run(scenario())
    assert first.closed and first is not second
    assert first.expected_state != second.expected_state and first_url != second_url
    assert h.service.status().state == "connected"


def test_connect_when_already_connected_changes_nothing(tmp_path) -> None:
    # Changed: a sign-in file exists · Then: no Kaggle call, no listener, still connected · Demonstrates: no accidental re-consent
    h = Harness(tmp_path, saved=SAVED)
    assert run(h.service.start_connect()) is None
    assert h.kaggle.requests == [] and FakeListener.created == []
    assert h.service.status().state == "connected"


def test_cancel_on_kaggle_saves_nothing(tmp_path) -> None:
    # Changed: the callback says access_denied · Then: no file, disconnected, reason cancelled · Demonstrates: Cancel on Kaggle saves nothing
    h = Harness(tmp_path)
    run(h.connect_and_come_back(CallbackResult("cancelled")))
    assert h.file.load() is None and not h.file.path.exists()
    assert h.service.status() == KaggleAccountStatus("disconnected", notice=CANCELLED_NOTICE)
    assert h.kaggle.calls_to(oauth.TOKEN_URL) == []


def test_timeout_saves_nothing(tmp_path) -> None:
    # Changed: the listener times out · Then: no file, reason timed_out · Demonstrates: a forgotten sign-in saves nothing
    h = Harness(tmp_path)
    run(h.connect_and_come_back(CallbackResult("timed_out")))
    assert not h.file.path.exists()
    assert h.service.status().notice == TIMED_OUT_NOTICE


def test_exchange_refused_saves_nothing(tmp_path) -> None:
    # Changed: the token endpoint answers 400 · Then: no file, reason refused · Demonstrates: a refused sign-in saves nothing
    h = Harness(tmp_path, kaggle=FakeKaggle(token=answer(400, {"error": "invalid_request"})))
    run(h.connect_and_come_back(APPROVED))
    assert not h.file.path.exists()
    assert h.service.status() == KaggleAccountStatus("disconnected", notice=REFUSED_NOTICE)


def test_register_fails_before_opening_browser(tmp_path) -> None:
    # Changed: registration answers 500 · Then: a sign-in error, no authorize URL, no listener left open · Demonstrates: the user isn't sent to a dead page
    h = Harness(tmp_path, kaggle=FakeKaggle(register=answer(500)))
    with pytest.raises(WorkspaceError) as raised:
        run(h.service.start_connect())
    assert raised.value.code == ErrorCode.KAGGLE_SIGNIN
    assert raised.value.message == REFUSED_NOTICE
    assert h.listener.closed
    assert h.service.status().state == "disconnected"


def test_cancel_connect_closes_listener(tmp_path) -> None:
    # Changed: cancel while waiting · Then: listener closed, disconnected, no Kaggle call · Demonstrates: turning off while waiting works
    h = Harness(tmp_path)

    async def scenario():
        await h.service.start_connect()
        calls_before = len(h.kaggle.requests)
        await h.service.cancel_connect()
        return calls_before

    calls_before = run(scenario())
    assert h.listener.closed
    assert len(h.kaggle.requests) == calls_before
    assert h.service.status() == KaggleAccountStatus("disconnected", notice=CANCELLED_NOTICE)


# Baseline: Given a saved sign-in and an access token in memory · When disconnecting


def connected_harness(tmp_path, kaggle: FakeKaggle | None = None) -> Harness:
    h = Harness(tmp_path, kaggle=kaggle, saved=SAVED)
    run(h.service.access_token())  # puts an access token in memory
    return h


def test_disconnect_revokes_and_deletes(tmp_path) -> None:
    # Changed: — · Then: the refresh token is revoked on Kaggle, the file is gone, and access_token gives None · Demonstrates: disconnect
    h = connected_harness(tmp_path)
    run(h.service.disconnect())
    revoke = h.kaggle.calls_to(oauth.REVOKE_URL)
    assert len(revoke) == 1
    assert json.loads(revoke[0].content)["token"] == REFRESH_TOKEN
    assert not h.file.path.exists()
    assert run(h.service.access_token()) is None
    assert h.changes[-1] == KaggleAccountStatus("disconnected")


def test_disconnect_keeps_downloaded_datasets(tmp_path) -> None:
    # Changed: a project with a ready pooled dataset · Then: pool and project rows are untouched · Demonstrates: downloaded datasets stay
    workspaces = tmp_path / "workspaces"
    (workspaces / "pool" / "kaggle-x--y@1").mkdir(parents=True)
    (workspaces / "pool" / "kaggle-x--y@1" / "Iris.csv").write_text("a,b\n1,2\n")
    (workspaces / "researchchat.db").write_bytes(b"sqlite rows")
    before = {p: p.read_bytes() for p in workspaces.rglob("*") if p.is_file()}
    h = connected_harness(tmp_path)
    run(h.service.disconnect())
    assert {p: p.read_bytes() for p in workspaces.rglob("*") if p.is_file()} == before


def test_disconnect_when_not_connected_is_harmless(tmp_path) -> None:
    # Changed: no file · Then: no Kaggle call, disconnected · Demonstrates: disconnect can be repeated
    h = Harness(tmp_path)
    run(h.service.disconnect())
    run(h.service.disconnect())
    assert h.kaggle.requests == []
    assert h.service.status() == KaggleAccountStatus("disconnected")


def test_disconnect_when_kaggle_unreachable_still_deletes(tmp_path) -> None:
    # Changed: revoke raises ConnectError · Then: the file is gone, reason revoke_unreachable, access_token gives None · Demonstrates: the sign-in leaves this computer even when Kaggle is down
    h = connected_harness(tmp_path, kaggle=FakeKaggle(revoke=network_down))
    run(h.service.disconnect())
    assert not h.file.path.exists()
    assert h.service.status() == KaggleAccountStatus("disconnected", notice=REVOKE_UNREACHABLE_NOTICE)
    assert run(h.service.access_token()) is None


# Baseline: Given a saved sign-in and the clock at a fixed time · When a download asks for an access token


def test_first_call_refreshes_then_reuses(tmp_path) -> None:
    # Changed: two calls within 3 hours · Then: one refresh, the same token twice · Demonstrates: no refresh per download
    h = Harness(tmp_path, saved=SAVED)
    first = run(h.service.access_token())
    h.clock.seconds += 60 * 60
    second = run(h.service.access_token())
    assert first == second == REFRESHED_ACCESS_TOKEN
    assert len(h.kaggle.calls_to(oauth.TOKEN_URL)) == 1


def test_expired_token_is_refreshed(tmp_path) -> None:
    # Changed: the clock moves on 3 hours · Then: a second refresh · Demonstrates: the user stays signed in
    h = Harness(tmp_path, saved=SAVED)
    run(h.service.access_token())
    h.clock.seconds += THREE_HOURS
    run(h.service.access_token())
    assert len(h.kaggle.calls_to(oauth.TOKEN_URL)) == 2


def test_parallel_calls_refresh_once(tmp_path) -> None:
    # Changed: five calls at once · Then: exactly one refresh request · Demonstrates: parallel downloads don't race
    h = Harness(tmp_path, saved=SAVED)

    async def five_at_once():
        return await asyncio.gather(*(h.service.access_token() for _ in range(5)))

    assert set(run(five_at_once())) == {REFRESHED_ACCESS_TOKEN}
    assert len(h.kaggle.calls_to(oauth.TOKEN_URL)) == 1


def test_same_account_for_every_project(tmp_path) -> None:
    # Changed: callers from two projects · Then: both get the same token from one file · Demonstrates: one account for all projects
    h = Harness(tmp_path, saved=SAVED)
    project_a_token = run(h.service.access_token())
    other_service_same_file = KaggleAccountService(h.file, h.kaggle.client, FakeListener, 600, h.clock, h._record)
    project_b_token = run(other_service_same_file.access_token())
    assert project_a_token == project_b_token == REFRESHED_ACCESS_TOKEN
    assert [p.name for p in tmp_path.iterdir()] == ["kaggle-account.json"]


def test_not_connected_returns_none(tmp_path) -> None:
    # Changed: no file · Then: None and no Kaggle call · Demonstrates: downloads can go signed out
    h = Harness(tmp_path)
    assert run(h.service.access_token()) is None
    assert h.kaggle.requests == []


def test_invalid_grant_forgets_sign_in(tmp_path) -> None:
    # Changed: refresh answers 400 invalid_grant · Then: None, the file is deleted, the signed-out notice is set and announced · Demonstrates: Kaggle signing the user out is handled
    kaggle = FakeKaggle(token=answer(400, {"error": "invalid_grant", "error_description": "Invalid refresh token"}))
    h = Harness(tmp_path, kaggle=kaggle, saved=SAVED)
    assert run(h.service.access_token()) is None
    assert not h.file.path.exists()
    expected = KaggleAccountStatus("disconnected", notice=SIGNED_OUT_NOTICE)
    assert h.service.status() == expected
    assert h.changes == [expected]


def test_network_error_keeps_sign_in(tmp_path) -> None:
    # Changed: refresh raises ConnectError · Then: None for this call and the file is kept · Demonstrates: a flaky network doesn't sign the user out
    h = Harness(tmp_path, kaggle=FakeKaggle(token=network_down), saved=SAVED)
    assert run(h.service.access_token()) is None
    assert h.file.load() == SAVED
    assert h.changes == []
