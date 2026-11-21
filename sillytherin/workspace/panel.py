"""The Notebook panel of every open chat, and live updates to all of them.

A push for one project reaches every chat showing it, each through its own panel sink.
"""

import asyncio
import contextvars

from sillytherin.chat.ports import PanelSink
from sillytherin.workspace.service import NotebookProps

# Set during an edit action: the acting chat gets the result as the action's
# reply, so it isn't pushed there too (a push while typing would cost the cursor).
skip_session: contextvars.ContextVar[str | None] = contextvars.ContextVar("skip_session", default=None)


class PanelRegistry:
    """Which chats show which project's panel, so changes reach all of them."""

    def __init__(self) -> None:
        self._panels: dict[str, dict[str, PanelSink]] = {}  # project_id -> {chat_id: sink}

    def open(self, project_id: str, chat_id: str, sink: PanelSink) -> None:
        """Show this chat's panel on `project_id` from now on (a chat shows one project at a time)."""
        self.unregister(chat_id)
        self._panels.setdefault(project_id, {})[chat_id] = sink

    def unregister(self, chat_id: str) -> None:
        """Forget a closed chat's panel."""
        for panels in self._panels.values():
            panels.pop(chat_id, None)

    async def push(self, project_id: str, props: NotebookProps) -> None:
        """Send new props to every open panel of the project; a closed tab is skipped."""
        skip = skip_session.get()
        sinks = [sink for chat_id, sink in self._panels.get(project_id, {}).items() if chat_id != skip]
        await asyncio.gather(*(sink.show_panel(props) for sink in sinks), return_exceptions=True)
