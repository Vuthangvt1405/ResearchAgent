"""The messages the page and the server send each other over a chat's WebSocket.

Every message is JSON with a `type`. Page events are checked strictly: a wrong type is
refused rather than converted, and fields the page may not set are dropped.
"""

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from researchchat.chat.ports import Choice, ToastKind
from researchchat.chat.widgets import Picker, SettingSwitch

MAX_MESSAGE_CHARS = 100_000
MAX_FRAME_BYTES = 1_048_576  # one socket message; bigger closes the socket
MAX_ID_CHARS = 64


class EventError(StrEnum):
    BAD_EVENT = "BAD_EVENT"  # not JSON, unknown type, missing or wrong field
    BUSY = "BUSY"  # a message arrived while this chat's reply is still running
    UNKNOWN_ASK = "UNKNOWN_ASK"  # an answer to a prompt this chat doesn't have open
    INTERNAL = "INTERNAL"  # a handler failed; details stay in the app log


# ---- page → server


class PageEvent(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)


class ChatSend(PageEvent):
    """You sent a message, with the pickers' current choices."""

    type: Literal["chat.send"]
    text: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    model: str = Field(max_length=200)
    effort: str = Field(max_length=MAX_ID_CHARS)


class ChatStop(PageEvent):
    """The Stop button."""

    type: Literal["chat.stop"]


class SettingsUpdate(PageEvent):
    """A Settings switch changed; values apply right away."""

    type: Literal["settings.update"]
    values: dict[str, bool]


class AskAnswer(PageEvent):
    """You clicked a choice under a prompt."""

    type: Literal["ask.answer"]
    ask_id: str = Field(min_length=1, max_length=MAX_ID_CHARS)
    choice: str = Field(min_length=1, max_length=MAX_ID_CHARS)


class PanelAction(PageEvent):
    """A Notebook panel action; `name` and `payload` are checked against the panel's own allow-list."""

    type: Literal["panel.action"]
    request_id: str = Field(min_length=1, max_length=MAX_ID_CHARS)
    name: str = Field(min_length=1, max_length=MAX_ID_CHARS)
    payload: dict[str, Any]


AnyPageEvent = Annotated[ChatSend | ChatStop | SettingsUpdate | AskAnswer | PanelAction, Field(discriminator="type")]


_PAGE_EVENTS: TypeAdapter[PageEvent] = TypeAdapter(AnyPageEvent)


def parse_page_event(frame: str) -> PageEvent:
    """The event in one socket frame; raises ValueError for anything that isn't a valid page event."""
    try:
        return _PAGE_EVENTS.validate_json(frame)
    except ValidationError as e:
        raise ValueError("Not a valid event.") from e


# ---- server → page


class ServerEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ChatLine(BaseModel):
    """One message already in the chat, so a reconnected page can redraw it."""

    model_config = ConfigDict(frozen=True)

    role: Literal["user", "assistant"]
    text: str


class SessionReady(ServerEvent):
    """The chat is open: everything the page draws first."""

    type: Literal["session.ready"] = "session.ready"
    chat_id: str
    messages: list[ChatLine]  # empty for a new chat; the chat so far after a reconnect
    pickers: list[Picker]
    settings: list[SettingSwitch]
    panel: dict[str, Any]  # NotebookProps of the chat's project


class ChatClosed(ServerEvent):
    """The chat the page asked to resume no longer exists (the app restarted); a new one follows."""

    type: Literal["chat.closed"] = "chat.closed"


class ReplyStarted(ServerEvent):
    type: Literal["reply.started"] = "reply.started"
    message_id: str


class ReplyDelta(ServerEvent):
    type: Literal["reply.delta"] = "reply.delta"
    message_id: str
    text: str


class ReplyEnded(ServerEvent):
    """The reply's final text, including a partial answer after Stop or an "Error: …" text."""

    type: Literal["reply.ended"] = "reply.ended"
    message_id: str
    text: str


class GroupLabel(ServerEvent):
    """The reply's work group shows what is happening now."""

    type: Literal["group.label"] = "group.label"
    message_id: str
    label: str


class GroupDone(ServerEvent):
    """The work group's summary, such as "4 steps · 12s"."""

    type: Literal["group.done"] = "group.done"
    message_id: str
    label: str


class ThinkingDelta(ServerEvent):
    type: Literal["thinking.delta"] = "thinking.delta"
    message_id: str
    text: str


class StepDone(ServerEvent):
    type: Literal["step.done"] = "step.done"
    message_id: str
    title: str
    output: str


class ChatMessage(ServerEvent):
    """A message from outside the reply, such as a finished download."""

    type: Literal["chat.message"] = "chat.message"
    text: str


class AskOpened(ServerEvent):
    type: Literal["ask.opened"] = "ask.opened"
    ask_id: str
    markdown: str
    choices: list[Choice]


class AskClosed(ServerEvent):
    """The prompt was answered or timed out; `choice` is None on timeout."""

    type: Literal["ask.closed"] = "ask.closed"
    ask_id: str
    choice: str | None


class Toast(ServerEvent):
    type: Literal["toast"] = "toast"
    kind: ToastKind
    text: str


class SettingsChanged(ServerEvent):
    type: Literal["settings.changed"] = "settings.changed"
    switches: list[SettingSwitch]


class PickersChanged(ServerEvent):
    type: Literal["pickers.changed"] = "pickers.changed"
    pickers: list[Picker]


class PanelPropsEvent(ServerEvent):
    """New panel props pushed from another tab or a download."""

    type: Literal["panel.props"] = "panel.props"
    props: dict[str, Any]


class PanelResult(ServerEvent):
    """The reply to one `panel.action`: props, or props with `error`."""

    type: Literal["panel.result"] = "panel.result"
    request_id: str
    result: dict[str, Any] | list[Any]


class KagglePopup(ServerEvent):
    type: Literal["kaggle.popup"] = "kaggle.popup"
    state: Literal["waiting", "connected", "failed"]
    authorize_url: str
    message: str


class ErrorEvent(ServerEvent):
    """A refused event; never a stack trace."""

    type: Literal["error"] = "error"
    code: EventError
    message: str
