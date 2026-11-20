"""The Kaggle account switch in Settings and the sign-in pop-up in the chat."""

import asyncio
import contextvars
import re
from pathlib import Path

from researchchat.settings import build_widgets
from researchchat.workspace.kaggle import settings_switch as switch
from researchchat.workspace.kaggle.account import (
    CANCELLED_NOTICE,
    REFUSED_NOTICE,
    KaggleAccountStatus,
)
from researchchat.workspace.kaggle.callback import CallbackResult
from researchchat.workspace.kaggle.settings_switch import (
    ChatSide,
    account_change,
    apply_account_change,
    kaggle_switch,
)
from tests.kaggle.fakes import USERNAME, FakeKaggle, FakeListener, answer
from tests.kaggle.test_kaggle_account import SAVED, Harness

SIGN_IN_ELEMENT = Path(__file__).resolve().parents[2] / "public" / "elements" / "KaggleSignIn.jsx"


def run(coro):
    return asyncio.run(coro)


class FakePopup:
    def __init__(self) -> None:
        self.shown: list[str] = []
        self.finished: list[tuple[str, str]] = []

    async def show(self, authorize_url: str) -> None:
        self.shown.append(authorize_url)

    async def finish(self, state: str, message: str) -> None:
        self.finished.append((state, message))


class FakeChat:
    """The acting chat: records what the browser, pop-up, toasts and Settings were asked to do."""

    def __init__(self) -> None:
        self.opened: list[str] = []
        self.popup = FakePopup()
        self.toasts: list[tuple[str, str]] = []
        self.settings_resent = 0

    def side(self) -> ChatSide:
        return ChatSide(open_browser=self._open, popup=self.popup, send_toast=self._toast, resend_settings=self._resend)

    def _open(self, url: str) -> bool:
        self.opened.append(url)
        return True

    async def _toast(self, message: str, kind: str) -> None:
        self.toasts.append((message, kind))

    async def _resend(self) -> None:
        self.settings_resent += 1


async def settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


# Baseline: Given a disconnected account, a fake browser opener, a fake toast and a fake chat · When Settings are confirmed with the Kaggle switch turned from off to on


def test_turning_on_opens_browser_and_shows_popup(tmp_path) -> None:
    # Changed: — · Then: one connect, the browser and a waiting sign-in pop-up get the same authorize URL, and the waiting toast shows · Demonstrates: connecting starts
    h, chat = Harness(tmp_path), FakeChat()

    async def scenario():
        await apply_account_change("connect", h.service, chat.side())
        await h.service.cancel_connect()
        await settle()

    run(scenario())
    assert len(chat.opened) == 1 and chat.popup.shown == chat.opened
    assert chat.opened[0].startswith("https://www.kaggle.com/api/v1/oauth2/authorize?")
    assert chat.toasts[0] == (switch.WAITING_TOAST, "info")
    assert len(FakeListener.created) == 1


def test_switch_shows_connected_username() -> None:
    # Changed: switch built for connected as ana · Then: on, with 'Connected as ana.' · Demonstrates: Settings shows who is connected
    widget = kaggle_switch(KaggleAccountStatus("connected", username="ana"))
    assert (widget.id, widget.label, widget.initial) == ("kaggle_account", "Kaggle account", True)
    assert widget.description == "Connected as ana."


def test_switch_shows_not_connected() -> None:
    # Changed: switch built for disconnected · Then: off, with the Connect description and the private-datasets note · Demonstrates: the user knows how to connect
    widget = kaggle_switch(KaggleAccountStatus("disconnected"))
    assert widget.initial is False
    assert widget.description == "Not connected. Connect to sign in with Kaggle in your browser. Public datasets work without an account. To use your private or own Kaggle datasets, connect first."
    signed_out = kaggle_switch(KaggleAccountStatus("disconnected", notice="Kaggle signed you out. Connect to sign in again."))
    assert signed_out.description == (
        "Kaggle signed you out. Connect to sign in again."
        " Public datasets work without an account. To use your private or own Kaggle datasets, connect first."
    )


def test_account_change_resends_settings_to_every_chat(monkeypatch) -> None:
    # Changed: two live chats; the account becomes connected · Then: both get Settings with the switch on, each with its own model widgets · Demonstrates: one account for every open chat
    from researchchat.workspace import actions

    current_chat: contextvars.ContextVar[str] = contextvars.ContextVar("current_chat")
    received: dict[str, list] = {}

    class Session:
        def __init__(self, session_id: str) -> None:
            self.id = session_id

    async def build_for(status: KaggleAccountStatus) -> list:
        return build_widgets({"reasoning"}, kaggle=status)

    async def record_resend(build) -> None:
        received[current_chat.get()] = await build()

    registry = actions.ChatRegistry()
    registry.register(Session("chat-a"))
    registry.register(Session("chat-b"))
    monkeypatch.setattr(actions, "chats", registry)
    monkeypatch.setattr(actions, "settings_widgets", build_for)
    monkeypatch.setattr(actions, "init_ws_context", lambda session: current_chat.set(session.id))
    monkeypatch.setattr(actions, "resend_settings_here", record_resend)

    run(actions.refresh_kaggle_switch_everywhere(KaggleAccountStatus("connected", username=USERNAME)))
    assert sorted(received) == ["chat-a", "chat-b"]
    for widgets in received.values():
        assert [w.id for w in widgets] == ["show_thinking", "web_search", "notebook", "kaggle_account"]
        assert widgets[-1].initial is True


def test_turning_off_disconnects(tmp_path) -> None:
    # Changed: connected; switch on to off · Then: disconnect, toast 'Kaggle disconnected.' · Demonstrates: disconnecting from Settings
    h, chat = Harness(tmp_path, saved=SAVED), FakeChat()
    run(apply_account_change("disconnect", h.service, chat.side()))
    assert not h.file.path.exists()
    assert chat.toasts == [(switch.DISCONNECTED_TOAST, "info")]


def test_turning_off_while_waiting_cancels(tmp_path) -> None:
    # Changed: connecting; switch on to off · Then: the sign-in is cancelled, toast 'Kaggle sign-in was cancelled.' · Demonstrates: the user can back out
    h, chat = Harness(tmp_path), FakeChat()

    async def scenario():
        await apply_account_change("connect", h.service, chat.side())
        await apply_account_change("disconnect", h.service, chat.side())
        await settle()

    run(scenario())
    assert h.listener.closed
    assert (CANCELLED_NOTICE, "warning") in chat.toasts
    assert chat.popup.finished == [("failed", CANCELLED_NOTICE)]
    assert not h.file.path.exists()


def test_settings_shown_for_model_without_tools() -> None:
    # Changed: a model with no reasoning or tools · Then: the Kaggle switch is the only row that can be changed · Demonstrates: connecting works whatever the model
    widgets = build_widgets(set(), kaggle=KaggleAccountStatus("disconnected"))
    assert [w.id for w in widgets if not w.disabled] == ["kaggle_account"]


def test_account_change_is_pure() -> None:
    # Changed: every pair of before and after values · Then: connect, disconnect or nothing · Demonstrates: the rule is one small function
    assert account_change(False, True) == "connect"
    assert account_change(True, False) == "disconnect"
    assert account_change(True, True) is None
    assert account_change(False, False) is None


def test_popup_updates_when_sign_in_ends(tmp_path) -> None:
    # Changed: the sign-in finishes, or fails · Then: the same pop-up turns connected with 'Kaggle connected as ana', or failed with the reason · Demonstrates: the dialog closes itself
    async def connect_then(result: CallbackResult, folder: str, kaggle: FakeKaggle | None = None) -> FakeChat:
        h, chat = Harness(tmp_path / folder, kaggle=kaggle), FakeChat()
        await apply_account_change("connect", h.service, chat.side())
        h.listener.come_back(result)
        await h.service.wait_for_sign_in()
        await settle()
        return chat

    approved = run(connect_then(CallbackResult("code", "approval-code-1"), "approved"))
    assert approved.popup.finished == [("connected", f"Kaggle connected as {USERNAME}")]
    assert approved.toasts[-1] == (f"Kaggle connected as {USERNAME}", "success")
    refused = run(connect_then(CallbackResult("code", "approval-code-1"), "refused", kaggle=FakeKaggle(token=answer(400))))
    assert refused.popup.finished == [("failed", REFUSED_NOTICE)]


def test_unchanged_switch_does_nothing(monkeypatch) -> None:
    # Changed: other settings change, the switch doesn't · Then: no account call, no toast · Demonstrates: changing thinking effort doesn't touch Kaggle
    from researchchat.workspace import actions

    applied: list[str] = []

    async def record(change, _account, _chat) -> None:
        applied.append(change)

    async def build_for(status: KaggleAccountStatus) -> list:
        return []

    monkeypatch.setattr(actions, "settings_widgets", build_for)
    monkeypatch.setattr(actions, "apply_account_change", record)
    for switch_value in (False, True):
        before = {"thinking_effort": "low", "kaggle_account": switch_value}
        after = {"thinking_effort": "high", "kaggle_account": switch_value}
        run(actions.apply_kaggle_switch(before, after))
    assert applied == []


def test_registration_failure_turns_switch_back_off(tmp_path) -> None:
    # Changed: connecting fails before the browser step · Then: no browser, no pop-up; Settings re-sent off; toast 'Couldn't connect to Kaggle. Try again.' · Demonstrates: a failed start is clear
    h, chat = Harness(tmp_path, kaggle=FakeKaggle(register=answer(500))), FakeChat()
    run(apply_account_change("connect", h.service, chat.side()))
    assert chat.opened == [] and chat.popup.shown == []
    assert chat.settings_resent == 1
    assert chat.toasts == [(REFUSED_NOTICE, "error")]
    assert h.service.status().state == "disconnected"


def test_only_kaggle_authorize_url_is_opened(tmp_path, monkeypatch) -> None:
    # Changed: the connect step returns a non-Kaggle URL · Then: nothing opened, no pop-up, the couldn't-connect toast · Demonstrates: the app opens only Kaggle's approval page
    h, chat = Harness(tmp_path), FakeChat()
    real_start = h.service.start_connect

    async def crafted_start() -> str:
        await real_start()
        return "https://evil.example/api/v1/oauth2/authorize?state=x"

    monkeypatch.setattr(h.service, "start_connect", crafted_start)
    run(apply_account_change("connect", h.service, chat.side()))
    assert chat.opened == [] and chat.popup.shown == []
    assert chat.toasts == [(REFUSED_NOTICE, "error")]
    assert h.listener.closed


def test_sign_in_element_opens_only_kaggle_url() -> None:
    # Changed: read the sign-in element's source · Then: window.open is guarded by the Kaggle authorize prefix; no dangerouslySetInnerHTML or eval · Demonstrates: the browser side opens only Kaggle
    source = SIGN_IN_ELEMENT.read_text()
    assert 'const KAGGLE_AUTHORIZE_PREFIX = "https://www.kaggle.com/api/v1/oauth2/authorize?";' in source
    assert re.search(r"startsWith\(KAGGLE_AUTHORIZE_PREFIX\)", source)
    assert source.count("window.open(") == 1
    guarded_open = re.search(r"if \(!isKaggleAuthorizeUrl\(url\)\) return;\s*window\.open\(url", source)
    assert guarded_open, "window.open must come right after the Kaggle prefix check"
    for forbidden in ("dangerouslySetInnerHTML", "eval(", "innerHTML"):
        assert forbidden not in source
