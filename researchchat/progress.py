"""One collapsible group per reply that holds all its work (thinking, searches,
page reads). Its title shows what is happening right now, then a summary."""

import time
from collections.abc import Callable

from researchchat.chat.ports import ProgressView, ThinkingStep, ToolStep

THINKING_LABEL = "Thinking"


class Progress:
    """Counts one reply's steps and time; `view` draws the group."""

    def __init__(self, view: ProgressView, clock: Callable[[], float] = time.monotonic) -> None:
        self.view = view
        self.clock = clock
        self.steps = 0
        self.started = clock()
        self.label: str | None = None

    @property
    def is_open(self) -> bool:
        return self.label is not None

    async def now(self, label: str) -> None:
        """Show `label` as the current activity, opening the group if needed."""
        if label != self.label:
            self.label = label
            await self.view.show_activity(label)

    async def step_started(self, label: str) -> None:
        self.steps += 1
        await self.now(label)

    async def start_thinking(self) -> ThinkingStep:
        await self.step_started(THINKING_LABEL)
        return await self.view.start_thinking()

    async def start_tool_step(self, title: str) -> ToolStep:
        await self.step_started(title)
        return await self.view.start_tool_step(title)

    async def finish(self) -> None:
        """Close the group with a summary title, e.g. "4 steps · 12s"."""
        if not self.is_open:
            return
        seconds = round(self.clock() - self.started)
        plural = "" if self.steps == 1 else "s"
        await self.view.close(f"{self.steps} step{plural} · {seconds}s")
        self.label = None
