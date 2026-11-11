"""One collapsible group per reply that holds all its work (thinking, searches,
page reads). Its title shows what is happening right now, then a summary."""

import time

import chainlit as cl

# Chainlit loads a step's icon from /avatars/<step name> and rejects names with
# ":" or "·" (a blank circle shows instead). This makes steps use the app's icon.
STEP_AVATAR = {"avatarName": "default"}


class Progress:
    def __init__(self) -> None:
        self.group: cl.Step | None = None
        self.steps = 0
        self.started = time.monotonic()

    async def now(self, label: str) -> None:
        """Show `label` as the current activity, opening the group if needed.

        Steps created after this (until finish) are nested inside the group,
        because Chainlit parents new steps to the step that is open.
        """
        if self.group is None:
            self.group = cl.Step(name=label, type="run", default_open=False, metadata=dict(STEP_AVATAR))
            await self.group.__aenter__()
        elif self.group.name != label:
            self.group.name = label
            await self.group.update()

    async def step_started(self, label: str) -> None:
        """Call before creating a nested step."""
        self.steps += 1
        await self.now(label)

    async def finish(self) -> None:
        """Close the group with a summary title, e.g. "4 steps · 12s"."""
        if self.group is None:
            return
        seconds = round(time.monotonic() - self.started)
        plural = "" if self.steps == 1 else "s"
        self.group.name = f"{self.steps} step{plural} · {seconds}s"
        await self.group.__aexit__(None, None, None)
        self.group = None
