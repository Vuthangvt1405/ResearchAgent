"""Small Protocols for everything the business code shows in, or asks of, one chat.

Each Protocol is one job, so a tool depends only on what it uses: a prompt needs an
`Asker`, a tool step needs a `ProgressView`, nothing needs the whole chat UI.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from researchchat.chat.widgets import Picker, SettingSwitch
from researchchat.workspace.service import NotebookProps

ToastKind = Literal["info", "success", "warning", "error"]


@dataclass(frozen=True)
class Choice:
    """One button under a prompt: `id` comes back when it is clicked, `label` is what it says."""

    id: str
    label: str


class AnswerView(Protocol):
    """The reply the model's answer streams into."""

    async def stream(self, text: str) -> None: ...

    async def finish(self, text: str) -> None: ...


class ThinkingStep(Protocol):
    """The model's reasoning, shown as a step inside the reply's work group."""

    async def stream(self, text: str) -> None: ...

    async def close(self) -> None: ...


class ToolStep(Protocol):
    """One tool call, shown as a step inside the reply's work group while it runs."""

    async def finish(self, output: str) -> None: ...


class ProgressView(Protocol):
    """The collapsible group that holds one reply's work: its label, thinking and tool steps."""

    async def show_activity(self, label: str) -> None: ...

    async def start_thinking(self) -> ThinkingStep: ...

    async def start_tool_step(self, title: str) -> ToolStep: ...

    async def close(self, summary: str) -> None: ...


class Asker(Protocol):
    """A Run / Skip style prompt in the chat."""

    async def ask_choice(self, markdown: str, choices: Sequence[Choice], timeout_seconds: int) -> str | None:
        """The id of the clicked choice, or None when nobody answered in time."""
        ...


class Toaster(Protocol):
    async def show_toast(self, text: str, kind: ToastKind) -> None: ...


class ChatPoster(Protocol):
    """Posts a message into one chat from outside its reply, such as a finished download."""

    async def post(self, text: str) -> None: ...


class PanelSink(Protocol):
    """One chat's Notebook panel."""

    async def show_panel(self, props: NotebookProps) -> None: ...


class SettingsView(Protocol):
    """One chat's Settings and chat box pickers."""

    async def show_settings(self, switches: Sequence[SettingSwitch]) -> dict[str, bool]:
        """Show Settings; returns the values each switch starts at."""
        ...

    async def show_pickers(self, pickers: Sequence[Picker]) -> None: ...


class ChatState(Protocol):
    """Values one chat keeps while it is open: its history, picks, settings and project."""

    @property
    def chat_id(self) -> str: ...

    def get(self, key: str) -> object | None: ...

    def set(self, key: str, value: object) -> None: ...
