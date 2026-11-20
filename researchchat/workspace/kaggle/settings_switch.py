"""The "Kaggle account" setting, and what connecting or disconnecting does.

Chainlit's Settings has no button widget, so the setting is sent as a switch and
public/custom.js draws a Connect / Disconnect button in its place; the button flips
the switch and presses Confirm. Connecting opens Kaggle's page in the browser and
pops up a sign-in dialog in the chat.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol

import chainlit as cl
from chainlit.input_widget import Switch

from researchchat.workspace import WorkspaceError
from researchchat.workspace.kaggle.account import (
    REFUSED_NOTICE,
    SIGNED_OUT_NOTICE,
    KaggleAccountService,
    KaggleAccountStatus,
)
from researchchat.workspace.kaggle.oauth import AUTHORIZE_URL

KAGGLE_SWITCH_ID = "kaggle_account"
KAGGLE_SWITCH_LABEL = "Kaggle account"
SIGN_IN_ELEMENT_NAME = "KaggleSignIn"  # public/elements/KaggleSignIn.jsx
WAITING_TOAST = "Waiting for Kaggle sign-in in your browser…"
DISCONNECTED_TOAST = "Kaggle disconnected."
WAITING_POPUP_MESSAGE = "Kaggle's approval page should have opened in your browser. If it didn't, open it here."
CONNECTED_DESCRIPTION = "Connected as {username}."
CONNECTING_DESCRIPTION = "Waiting for you to approve on Kaggle's page…"
NOT_CONNECTED_DESCRIPTION = "Not connected. Connect to sign in with Kaggle in your browser."
# Public Kaggle datasets download without an account; only private and the user's own need one
PRIVATE_DATASETS_NOTE = "Public datasets work without an account. To use your private or own Kaggle datasets, connect first."

AccountChange = Literal["connect", "disconnect"]
SignInPopupState = Literal["waiting", "connected", "failed"]
OpenBrowser = Callable[[str], bool]  # webbrowser.open
SendToast = Callable[[str, str], Awaitable[None]]  # (message, type)
ResendSettings = Callable[[], Awaitable[None]]


def kaggle_switch(status: KaggleAccountStatus) -> Switch:
    return Switch(
        id=KAGGLE_SWITCH_ID,
        label=KAGGLE_SWITCH_LABEL,
        initial=status.state != "disconnected",
        description=switch_description(status),
    )


def switch_description(status: KaggleAccountStatus) -> str:
    if status.state == "connected":
        return CONNECTED_DESCRIPTION.format(username=status.username)
    if status.state == "connecting":
        return CONNECTING_DESCRIPTION
    if status.notice == SIGNED_OUT_NOTICE:
        return f"{SIGNED_OUT_NOTICE} {PRIVATE_DATASETS_NOTE}"
    return f"{NOT_CONNECTED_DESCRIPTION} {PRIVATE_DATASETS_NOTE}"


def account_change(was_on: bool, now_on: bool) -> AccountChange | None:
    if was_on == now_on:
        return None
    return "connect" if now_on else "disconnect"


def is_kaggle_authorize_url(url: str) -> bool:
    return url.startswith(f"{AUTHORIZE_URL}?")


class SignInPopup(Protocol):
    """The sign-in dialog in the acting chat; updated in place when the sign-in ends."""

    async def show(self, authorize_url: str) -> None: ...

    async def finish(self, state: SignInPopupState, message: str) -> None: ...


class ChainlitSignInPopup:
    """The dialog as a Chainlit custom element inside one chat message."""

    def __init__(self) -> None:
        self._element: cl.CustomElement | None = None
        self._authorize_url = ""

    async def show(self, authorize_url: str) -> None:
        self._authorize_url = authorize_url
        self._element = cl.CustomElement(
            name=SIGN_IN_ELEMENT_NAME, props=self._props("waiting", WAITING_POPUP_MESSAGE), display="inline"
        )
        await cl.Message(content="", elements=[self._element]).send()

    async def finish(self, state: SignInPopupState, message: str) -> None:
        if self._element is None:
            return
        self._element.props = self._props(state, message)
        self._element.content = json.dumps(self._element.props)
        await self._element.update()

    def _props(self, state: SignInPopupState, message: str) -> dict:
        return {"authorize_url": self._authorize_url, "state": state, "message": message}


@dataclass(frozen=True)
class ChatSide:
    """What the acting chat can do while the account changes."""

    open_browser: OpenBrowser
    popup: SignInPopup
    send_toast: SendToast
    resend_settings: ResendSettings


_sign_in_watchers: set[asyncio.Task] = set()  # keeps the background waits alive until they finish


async def apply_account_change(change: AccountChange, account: KaggleAccountService, chat: ChatSide) -> None:
    if change == "connect":
        await connect_from_settings(account, chat)
    else:
        await disconnect_from_settings(account, chat)


async def connect_from_settings(account: KaggleAccountService, chat: ChatSide) -> None:
    try:
        authorize_url = await account.start_connect()
    except WorkspaceError as failure:
        await chat.resend_settings()
        await chat.send_toast(failure.message, "error")
        return
    if authorize_url is None:  # already connected: only the switch was stale
        await chat.resend_settings()
        return
    if not is_kaggle_authorize_url(authorize_url):
        await account.cancel_connect()
        await chat.send_toast(REFUSED_NOTICE, "error")
        return
    chat.open_browser(authorize_url)
    await chat.popup.show(authorize_url)
    await chat.send_toast(WAITING_TOAST, "info")
    watcher = asyncio.create_task(report_sign_in_result(account, chat))
    _sign_in_watchers.add(watcher)
    watcher.add_done_callback(_sign_in_watchers.discard)


async def report_sign_in_result(account: KaggleAccountService, chat: ChatSide) -> None:
    status = await account.wait_for_sign_in()
    if status.state == "connected":
        message = f"Kaggle connected as {status.username}"
        await chat.popup.finish("connected", message)
        await chat.send_toast(message, "success")
        return
    reason = status.notice or REFUSED_NOTICE
    await chat.popup.finish("failed", reason)
    await chat.send_toast(reason, "warning")


async def disconnect_from_settings(account: KaggleAccountService, chat: ChatSide) -> None:
    if account.status().state == "connecting":
        await account.cancel_connect()  # the sign-in watcher reports it in the pop-up and a toast
        return
    await account.disconnect()
    notice = account.status().notice
    await chat.send_toast(notice or DISCONNECTED_TOAST, "warning" if notice else "info")

