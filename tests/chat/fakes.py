"""Test doubles for the chat ports: they record what the business code showed or asked."""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field

from researchchat.chat.current import ChatContext, current_chat
from researchchat.chat.ports import Choice, ToastKind


@dataclass
class FakeToolStep:
    title: str
    output: str | None = None

    async def finish(self, output: str) -> None:
        self.output = output


@dataclass
class FakeThinkingStep:
    texts: list[str]
    is_closed: bool = False

    async def stream(self, text: str) -> None:
        self.texts.append(text)

    async def close(self) -> None:
        self.is_closed = True


@dataclass
class FakeProgressView:
    """Remembers every label, thinking text and tool step of one reply."""

    labels: list[str] = field(default_factory=list)
    tool_steps: list[FakeToolStep] = field(default_factory=list)
    thinking: list[str] = field(default_factory=list)
    summary: str | None = None

    async def show_activity(self, label: str) -> None:
        self.labels.append(label)

    async def start_thinking(self) -> FakeThinkingStep:
        return FakeThinkingStep(self.thinking)

    async def start_tool_step(self, title: str) -> FakeToolStep:
        step = FakeToolStep(title)
        self.tool_steps.append(step)
        return step

    async def close(self, summary: str) -> None:
        self.summary = summary


@dataclass
class FakeAnswerView:
    streamed: list[str] = field(default_factory=list)
    final: str | None = None

    async def stream(self, text: str) -> None:
        self.streamed.append(text)

    async def finish(self, text: str) -> None:
        self.final = text


@dataclass
class FakeAsker:
    """Answers every prompt with `answer` (None = nobody answered in time) and remembers what it was asked."""

    answer: str | None
    asked: list[tuple[str, list[Choice]]] = field(default_factory=list)

    async def ask_choice(self, markdown: str, choices: Sequence[Choice], timeout_seconds: int) -> str | None:
        self.asked.append((markdown, list(choices)))
        return self.answer


@dataclass
class FakeToaster:
    toasts: list[tuple[str, ToastKind]] = field(default_factory=list)

    async def show_toast(self, text: str, kind: ToastKind) -> None:
        self.toasts.append((text, kind))


@dataclass
class FakeChatState:
    """One chat's values in a plain dict."""

    chat_id: str = "chat-1"
    values: dict[str, object] = field(default_factory=dict)

    def get(self, key: str) -> object | None:
        return self.values.get(key)

    def set(self, key: str, value: object) -> None:
        self.values[key] = value


@contextmanager
def in_chat(state: FakeChatState | None = None, asker: FakeAsker | None = None, toaster: FakeToaster | None = None) -> Iterator[ChatContext]:
    """Run the block as if inside one chat's turn, then leave it."""
    chat = ChatContext(state or FakeChatState(), asker or FakeAsker(answer=None), toaster or FakeToaster())
    token = current_chat.set(chat)
    try:
        yield chat
    finally:
        current_chat.reset(token)
