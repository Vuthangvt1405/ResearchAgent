"""One WebSocket per chat: open or resume the chat, then handle the page's events one by one."""

import asyncio
import logging
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from researchchat.chat.current import ChatContext, current_chat
from researchchat.chat_start import (
    HISTORY_KEY,
    SETTINGS_KEY,
    current_picks,
    opening_controls,
    pickers_for,
    start_chat_values,
    switches_for,
)
from researchchat.server.events import (
    MAX_FRAME_BYTES,
    AskAnswer,
    ChatClosed,
    ChatLine,
    ChatSend,
    ChatStop,
    ErrorEvent,
    EventError,
    PageEvent,
    PanelAction,
    PanelResult,
    ServerEvent,
    SessionReady,
    SettingsUpdate,
    parse_page_event,
)
from researchchat.server.guard import is_allowed_host, is_allowed_origin
from researchchat.server.web_chat import (
    MemoryChatState,
    OpenPrompts,
    SocketAnswerView,
    SocketAsker,
    SocketChatPoster,
    SocketPanelSink,
    SocketProgressView,
    SocketSettingsView,
    SocketSignInPopup,
    SocketToaster,
)
from researchchat.settings import keep_chat_choices
from researchchat.turn import TurnViews, UserMessage, run_turn
from researchchat.workspace import actions

log = logging.getLogger(__name__)

# A tab that drops its socket (sleep, Wi-Fi blip) can reconnect to the same chat within this time;
# after it, the chat and its messages are deleted from memory
RECONNECT_GRACE_SECONDS = 120
CHAT_ID_BYTES = 16
POLICY_VIOLATION = 1008  # WebSocket close code: not the app's own page
MESSAGE_TOO_BIG = 1009
GENERIC_FAILURE = "Something went wrong; see the app log."


class ChatOutbox:
    """Sends a chat's events to whichever socket it has now; while it has none, events are dropped."""

    def __init__(self) -> None:
        self._socket: WebSocket | None = None

    def attach(self, socket: WebSocket) -> None:
        self._socket = socket

    def detach(self, socket: WebSocket) -> None:
        if self._socket is socket:
            self._socket = None

    async def send(self, event: ServerEvent) -> None:
        socket = self._socket
        if socket is None:
            return
        try:
            await socket.send_text(event.model_dump_json())
        except (WebSocketDisconnect, RuntimeError):
            self.detach(socket)  # the tab closed mid-send


@dataclass
class OpenChat:
    """A chat that lives while its tab is open, or for the grace period after its socket drops."""

    state: MemoryChatState
    outbox: ChatOutbox
    prompts: OpenPrompts
    link: actions.ChatLink
    asker: SocketAsker
    turn: asyncio.Task[None] | None = None  # the reply being written, if any
    tasks: set[asyncio.Task[None]] = field(default_factory=set)  # panel actions still running

    @property
    def chat_id(self) -> str:
        return self.state.chat_id

    @property
    def context(self) -> ChatContext:
        return ChatContext(self.state, self.asker, self.link.toaster)

    def is_replying(self) -> bool:
        return self.turn is not None and not self.turn.done()


def new_open_chat() -> OpenChat:
    state = MemoryChatState(secrets.token_urlsafe(CHAT_ID_BYTES))
    outbox = ChatOutbox()
    prompts = OpenPrompts()
    link = actions.ChatLink(
        state=state,
        poster=SocketChatPoster(outbox),
        settings=SocketSettingsView(outbox),
        toaster=SocketToaster(outbox),
        panel=SocketPanelSink(outbox),
        popup=SocketSignInPopup(outbox),
    )
    return OpenChat(state=state, outbox=outbox, prompts=prompts, link=link, asker=SocketAsker(outbox, prompts))


class ChatSessions:
    """Every open chat by id, so a reconnect finds its chat."""

    def __init__(self, grace_seconds: float = RECONNECT_GRACE_SECONDS) -> None:
        self.grace_seconds = grace_seconds
        self._chats: dict[str, OpenChat] = {}
        self._closers: dict[str, asyncio.TimerHandle] = {}

    def open_new(self) -> OpenChat:
        chat = new_open_chat()
        self._chats[chat.chat_id] = chat
        return chat

    def resume(self, chat_id: str) -> OpenChat | None:
        """The chat if it is still open or within its grace period; None after a restart or timeout."""
        closer = self._closers.pop(chat_id, None)
        if closer is not None:
            closer.cancel()
        return self._chats.get(chat_id)

    def detach(self, chat_id: str) -> None:
        """The socket is gone: delete the chat unless it reconnects within the grace period."""
        self._closers[chat_id] = asyncio.get_running_loop().call_later(self.grace_seconds, self.close, chat_id)

    def close(self, chat_id: str) -> None:
        self._closers.pop(chat_id, None)
        chat = self._chats.pop(chat_id, None)
        if chat is None:
            return
        if chat.is_replying():
            chat.turn.cancel()
        actions.close_chat(chat_id)

    def is_open(self, chat_id: str) -> bool:
        return chat_id in self._chats


async def serve_chat(websocket: WebSocket, sessions: ChatSessions, requested_chat_id: str | None, port: int) -> None:
    """Accept the socket from the app's own page, open or resume the chat, and handle its events."""
    is_own_page = is_allowed_origin(websocket.headers.get("origin"), port) and is_allowed_host(websocket.headers.get("host"), port)
    if not is_own_page:
        await websocket.close(code=POLICY_VIOLATION)
        return
    await websocket.accept()
    chat = sessions.resume(requested_chat_id) if requested_chat_id else None
    if chat is None:
        if requested_chat_id:
            await websocket.send_text(ChatClosed().model_dump_json())
        chat = sessions.open_new()
        chat.outbox.attach(websocket)
        await chat.outbox.send(await new_chat_ready(chat))
    else:
        chat.outbox.attach(websocket)
        await chat.outbox.send(await resumed_chat_ready(chat))
    try:
        await read_events(websocket, chat)
    except WebSocketDisconnect:
        pass
    finally:
        chat.outbox.detach(websocket)
        if sessions.is_open(chat.chat_id):
            sessions.detach(chat.chat_id)


async def new_chat_ready(chat: OpenChat) -> SessionReady:
    start_chat_values(chat.state)
    pickers, switches = await opening_controls(chat.state, actions.kaggle_account.status())
    panel = await actions.open_chat(chat.link)
    return SessionReady(chat_id=chat.chat_id, messages=[], pickers=pickers, settings=switches, panel=dict(panel))


async def resumed_chat_ready(chat: OpenChat) -> SessionReady:
    chosen = chat.state.get(SETTINGS_KEY) or {}
    switches = keep_chat_choices(await switches_for(chat.state, actions.kaggle_account.status()), chosen)
    panel = await actions.open_chat(chat.link)
    return SessionReady(
        chat_id=chat.chat_id,
        messages=visible_messages(chat.state.get(HISTORY_KEY) or []),
        pickers=await pickers_for(current_picks(chat.state)),
        settings=switches,
        panel=dict(panel),
    )


def visible_messages(history: list[dict]) -> list[ChatLine]:
    """What the user saw: their messages and the answers, without system notes or tool turns."""
    is_shown = {"user", "assistant"}
    return [ChatLine(role=m["role"], text=m["content"]) for m in history if m.get("role") in is_shown and m.get("content") and not m.get("tool_calls")]


async def read_events(websocket: WebSocket, chat: OpenChat) -> None:
    while True:
        frame = await websocket.receive_text()
        if len(frame.encode()) > MAX_FRAME_BYTES:
            await websocket.close(code=MESSAGE_TOO_BIG)
            return
        await handle_frame(chat, frame)


async def handle_frame(chat: OpenChat, frame: str) -> None:
    try:
        event = parse_page_event(frame)
    except ValueError:
        await refuse(chat, EventError.BAD_EVENT, "Not a valid event.")
        return
    try:
        await EVENT_HANDLERS[type(event)](chat, event)
    except Exception:
        log.exception("Handling %s failed", type(event).__name__)
        await refuse(chat, EventError.INTERNAL, GENERIC_FAILURE)


async def refuse(chat: OpenChat, code: EventError, message: str) -> None:
    await chat.outbox.send(ErrorEvent(code=code, message=message))


async def in_chat(chat: OpenChat, work: Awaitable[None]) -> None:
    """Run `work` as this chat's task, so tools deep inside find their chat."""
    current_chat.set(chat.context)
    await work


async def on_chat_send(chat: OpenChat, event: ChatSend) -> None:
    if chat.is_replying():
        await refuse(chat, EventError.BUSY, "Wait for the reply to finish, or press Stop.")
        return
    message_id = secrets.token_urlsafe(CHAT_ID_BYTES)
    views = TurnViews(
        answer=SocketAnswerView(chat.outbox, message_id),
        progress=SocketProgressView(chat.outbox, message_id),
        asker=chat.asker,
        settings=chat.link.settings,
    )
    message = UserMessage(text=event.text, model=event.model, effort=event.effort)
    chat.turn = asyncio.create_task(in_chat(chat, run_turn(chat.state, message, views)))


async def on_chat_stop(chat: OpenChat, event: ChatStop) -> None:
    if chat.is_replying():
        chat.turn.cancel()  # the turn keeps its partial answer and sends it as reply.ended


async def on_settings_update(chat: OpenChat, event: SettingsUpdate) -> None:
    switches = await switches_for(chat.state, actions.kaggle_account.status())
    changeable = {switch.id for switch in switches if not switch.disabled}
    previous: dict = dict(chat.state.get(SETTINGS_KEY) or {})
    updated = {**previous, **{key: value for key, value in event.values.items() if key in changeable}}
    chat.state.set(SETTINGS_KEY, updated)
    await actions.apply_kaggle_switch(previous, updated, chat.link)


async def on_ask_answer(chat: OpenChat, event: AskAnswer) -> None:
    outcome = chat.prompts.answer(event.ask_id, event.choice)
    if outcome == "unknown":
        await refuse(chat, EventError.UNKNOWN_ASK, "That question is no longer open.")
    elif outcome == "unoffered":
        await refuse(chat, EventError.BAD_EVENT, "Not one of the offered choices.")


async def on_panel_action(chat: OpenChat, event: PanelAction) -> None:
    """Panel actions run beside the chat (a cell may run for a while) and answer this tab when done."""

    async def run_action() -> None:
        current_chat.set(chat.context)
        try:
            result = await actions.run_panel_action(chat.link, event.name, event.payload)
        except Exception:
            log.exception("Panel action %s failed", event.name)
            await refuse(chat, EventError.INTERNAL, GENERIC_FAILURE)
            return
        await chat.outbox.send(PanelResult(request_id=event.request_id, result=result))

    task = asyncio.create_task(run_action())
    chat.tasks.add(task)
    task.add_done_callback(chat.tasks.discard)


EventHandler = Callable[[OpenChat, Any], Awaitable[None]]

# One handler per page event; a new event type adds an entry here
EVENT_HANDLERS: dict[type[PageEvent], EventHandler] = {
    ChatSend: on_chat_send,
    ChatStop: on_chat_stop,
    SettingsUpdate: on_settings_update,
    AskAnswer: on_ask_answer,
    PanelAction: on_panel_action,
}
