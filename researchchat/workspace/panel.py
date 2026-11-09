"""The right-side Notebook panel and live updates to every open panel.

Chainlit's sidebar only redraws when `set_sidebar_elements` is sent again with
a new key, so a push re-sends the element with fresh props to each session.
Pushes for other chats run in their own task with that chat's context.
"""

import asyncio
import contextvars
import itertools
import json
from dataclasses import dataclass

import chainlit as cl
from chainlit.context import init_ws_context

from researchchat.workspace.service import NotebookProps

ELEMENT_NAME = "Notebook"  # public/elements/Notebook.jsx
SIDEBAR_TITLE = "Notebook"

_keys = itertools.count(1)

# Set during an edit action: the acting chat gets the result as the action's
# reply, so it isn't pushed there too. (Chainlit recompiles a custom element on
# every props change, which would cost the user their cursor while typing.)
skip_session: contextvars.ContextVar[str | None] = contextvars.ContextVar("skip_session", default=None)


@dataclass
class _Panel:
    session: object  # chainlit WebsocketSession
    element: cl.CustomElement


async def _send(element: cl.CustomElement, props: NotebookProps) -> None:
    element.props = props
    element.content = json.dumps(props)
    await cl.context.emitter.emit(
        "set_sidebar_elements", {"elements": [element.to_dict()], "key": f"nb-{next(_keys)}"}
    )


class PanelRegistry:
    """Which chat sessions show which project's panel, so changes reach all of them."""

    def __init__(self):
        self._panels: dict[str, dict[str, _Panel]] = {}  # project_id -> {session_id: panel}

    async def open(self, project_id: str, props: NotebookProps) -> None:
        """Show the panel in the ElementSidebar for this session and register it."""
        session = cl.context.session
        self.unregister(session.id)
        element = cl.CustomElement(name=ELEMENT_NAME, props=props, display="side")
        await cl.ElementSidebar.set_title(SIDEBAR_TITLE)
        await cl.ElementSidebar.set_elements([element], key=f"nb-{next(_keys)}")
        self._panels.setdefault(project_id, {})[session.id] = _Panel(session, element)

    def unregister(self, session_id: str) -> None:
        """Forget a closed chat's panel."""
        for panels in self._panels.values():
            panels.pop(session_id, None)

    def sessions(self, project_id: str) -> list[str]:
        return list(self._panels.get(project_id, {}))

    async def push(self, project_id: str, props: NotebookProps) -> None:
        """Send new props to every open panel of the project."""

        async def one(panel: _Panel) -> None:
            init_ws_context(panel.session)  # only affects this task's context
            await _send(panel.element, props)

        skip = skip_session.get()
        panels = [p for sid, p in self._panels.get(project_id, {}).items() if sid != skip]
        tasks = [asyncio.create_task(one(p)) for p in panels]
        for result in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(result, Exception):
                pass  # a closed tab: the next unregister removes it
