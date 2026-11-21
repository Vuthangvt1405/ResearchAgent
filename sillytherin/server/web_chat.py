"""The chat ports for one browser tab: each one turns calls into events on that chat's socket."""

import asyncio
import secrets
from collections.abc import Sequence
from typing import Literal, Protocol

from sillytherin.chat.ports import Choice, ThinkingStep, ToastKind, ToolStep
from sillytherin.chat.widgets import Picker, SettingSwitch
from sillytherin.server.events import (
    AskClosed,
    AskOpened,
    ChatMessage,
    GroupDone,
    GroupLabel,
    KagglePopup,
    PanelPropsEvent,
    PickersChanged,
    ReplyDelta,
    ReplyEnded,
    ReplyStarted,
    ServerEvent,
    SettingsChanged,
    StepDone,
    ThinkingDelta,
    Toast,
)
from sillytherin.workspace.kaggle.settings_switch import (
    WAITING_POPUP_MESSAGE,
    SignInPopupState,
)
from sillytherin.workspace.service import NotebookProps

PROMPT_ID_BYTES = 16  # prompt ids are unguessable, so one chat can't answer another's prompt
AnswerOutcome = Literal["accepted", "unknown", "unoffered"]


class EventSender(Protocol):
    """Sends one event to the chat's page; a closed page drops it silently."""

    async def send(self, event: ServerEvent) -> None: ...


class MemoryChatState:
    """One chat's values, kept in memory only: they go when the chat closes."""

    def __init__(self, chat_id: str) -> None:
        self._chat_id = chat_id
        self._values: dict[str, object] = {}

    @property
    def chat_id(self) -> str:
        return self._chat_id

    def get(self, key: str) -> object | None:
        return self._values.get(key)

    def set(self, key: str, value: object) -> None:
        self._values[key] = value


class SocketAnswerView:
    def __init__(self, sender: EventSender, message_id: str) -> None:
        self._sender = sender
        self._message_id = message_id
        self._has_started = False

    async def stream(self, text: str) -> None:
        await self._start_once()
        await self._sender.send(ReplyDelta(message_id=self._message_id, text=text))

    async def finish(self, text: str) -> None:
        await self._start_once()
        await self._sender.send(ReplyEnded(message_id=self._message_id, text=text))

    async def _start_once(self) -> None:
        if not self._has_started:
            self._has_started = True
            await self._sender.send(ReplyStarted(message_id=self._message_id))


class SocketThinkingStep:
    def __init__(self, sender: EventSender, message_id: str) -> None:
        self._sender = sender
        self._message_id = message_id

    async def stream(self, text: str) -> None:
        await self._sender.send(ThinkingDelta(message_id=self._message_id, text=text))

    async def close(self) -> None:
        """The page closes the Thinking step when the answer starts, so there is nothing to send."""


class SocketToolStep:
    def __init__(self, sender: EventSender, message_id: str, title: str) -> None:
        self._sender = sender
        self._message_id = message_id
        self._title = title

    async def finish(self, output: str) -> None:
        await self._sender.send(StepDone(message_id=self._message_id, title=self._title, output=output))


class SocketProgressView:
    def __init__(self, sender: EventSender, message_id: str) -> None:
        self._sender = sender
        self._message_id = message_id

    async def show_activity(self, label: str) -> None:
        await self._sender.send(GroupLabel(message_id=self._message_id, label=label))

    async def start_thinking(self) -> ThinkingStep:
        return SocketThinkingStep(self._sender, self._message_id)

    async def start_tool_step(self, title: str) -> ToolStep:
        return SocketToolStep(self._sender, self._message_id, title)

    async def close(self, summary: str) -> None:
        await self._sender.send(GroupDone(message_id=self._message_id, label=summary))


class OpenPrompts:
    """The prompts one chat has open, by unguessable id; each id can be answered once."""

    def __init__(self) -> None:
        self._waiting: dict[str, tuple[frozenset[str], asyncio.Future[str]]] = {}

    def open(self, choices: Sequence[Choice]) -> tuple[str, asyncio.Future[str]]:
        ask_id = secrets.token_urlsafe(PROMPT_ID_BYTES)
        answer = asyncio.get_running_loop().create_future()
        self._waiting[ask_id] = (frozenset(choice.id for choice in choices), answer)
        return ask_id, answer

    def answer(self, ask_id: str, choice: str) -> AnswerOutcome:
        """Resolve the prompt; an unknown, closed or already answered id, or an unoffered choice, changes nothing."""
        waiting = self._waiting.get(ask_id)
        if waiting is None:
            return "unknown"
        offered, answer = waiting
        if choice not in offered:
            return "unoffered"
        del self._waiting[ask_id]
        answer.set_result(choice)
        return "accepted"

    def expire(self, ask_id: str) -> None:
        """Forget the prompt after a timeout, so a late answer is refused."""
        self._waiting.pop(ask_id, None)


class SocketAsker:
    def __init__(self, sender: EventSender, prompts: OpenPrompts) -> None:
        self._sender = sender
        self._prompts = prompts

    async def ask_choice(self, markdown: str, choices: Sequence[Choice], timeout_seconds: int) -> str | None:
        ask_id, answer = self._prompts.open(choices)
        await self._sender.send(AskOpened(ask_id=ask_id, markdown=markdown, choices=list(choices)))
        try:
            choice: str | None = await asyncio.wait_for(answer, timeout_seconds)
        except TimeoutError:
            choice = None  # nobody answered: the tool treats it as Skip
        finally:
            self._prompts.expire(ask_id)
        await self._sender.send(AskClosed(ask_id=ask_id, choice=choice))
        return choice


class SocketToaster:
    def __init__(self, sender: EventSender) -> None:
        self._sender = sender

    async def show_toast(self, text: str, kind: ToastKind) -> None:
        await self._sender.send(Toast(kind=kind, text=text))


class SocketChatPoster:
    def __init__(self, sender: EventSender) -> None:
        self._sender = sender

    async def post(self, text: str) -> None:
        await self._sender.send(ChatMessage(text=text))


class SocketPanelSink:
    def __init__(self, sender: EventSender) -> None:
        self._sender = sender

    async def show_panel(self, props: NotebookProps) -> None:
        await self._sender.send(PanelPropsEvent(props=dict(props)))


class SocketSettingsView:
    def __init__(self, sender: EventSender) -> None:
        self._sender = sender

    async def show_settings(self, switches: Sequence[SettingSwitch]) -> dict[str, bool]:
        await self._sender.send(SettingsChanged(switches=list(switches)))
        return {switch.id: switch.initial for switch in switches}

    async def show_pickers(self, pickers: Sequence[Picker]) -> None:
        await self._sender.send(PickersChanged(pickers=list(pickers)))


class SocketSignInPopup:
    """The Kaggle sign-in pop-up in the chat that turned the switch on."""

    def __init__(self, sender: EventSender) -> None:
        self._sender = sender
        self._authorize_url = ""

    async def show(self, authorize_url: str) -> None:
        self._authorize_url = authorize_url
        await self._sender.send(KagglePopup(state="waiting", authorize_url=authorize_url, message=WAITING_POPUP_MESSAGE))

    async def finish(self, state: SignInPopupState, message: str) -> None:
        await self._sender.send(KagglePopup(state=state, authorize_url=self._authorize_url, message=message))
