"""Action callbacks the Notebook panel calls with callAction (plan §4.2).

The project always comes from the chat session, never from the payload (SEC2).
Each callback returns NotebookProps, with `error` set when rejected.
"""

import asyncio
import logging

import chainlit as cl
from chainlit.context import init_ws_context

from researchchat.config import (
    DATASETS_ASK_ABOVE_MB,
    DATASETS_MAX_FILES,
    DATASETS_MIN_FREE_DISK_MB,
    DATASETS_PARALLEL_DOWNLOADS,
    DATASETS_STALL_TIMEOUT_SECONDS,
)
from researchchat.workspace import ErrorCode, WorkspaceError
from researchchat.workspace import store
from researchchat.workspace.dataset_service import DatasetService, DatasetsSettings
from researchchat.workspace.kernels import KernelRegistry
from researchchat.workspace.panel import PanelRegistry, skip_session
from researchchat.workspace.service import NotebookService

log = logging.getLogger(__name__)

kernels = KernelRegistry()
panels = PanelRegistry()
service = NotebookService(kernels, notify=panels.push)


class ChatRegistry:
    """Live Chainlit sessions by chat id, so a background job can message the chat that started it (NB-3)."""

    def __init__(self):
        self._sessions: dict[str, object] = {}  # session_id -> chainlit WebsocketSession

    def register(self, session) -> None:
        self._sessions[session.id] = session

    def unregister(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    async def send(self, session_id: str, text: str) -> bool:
        """Post a message in that chat's context; False when it's closed. Errors are swallowed."""
        session = self._sessions.get(session_id)
        if session is None:
            return False

        async def one() -> None:
            init_ws_context(session)  # only affects this task's context
            msg = cl.Message(content=text)
            msg.parent_id = None
            await msg.send()

        try:
            await asyncio.create_task(one())
            return True
        except Exception:
            log.warning("Couldn't message chat %s", session_id, exc_info=True)
            return False


chats = ChatRegistry()
datasets = DatasetService(
    settings=DatasetsSettings(
        min_free_disk_mb=DATASETS_MIN_FREE_DISK_MB,
        ask_above_mb=DATASETS_ASK_ABOVE_MB,
        max_files=DATASETS_MAX_FILES,
        parallel_downloads=DATASETS_PARALLEL_DOWNLOADS,
        stall_timeout_seconds=DATASETS_STALL_TIMEOUT_SECONDS,
    ),
    root=service.root,
    props=service.props,
    notify=panels.push,
    send=chats.send,
)
service.datasets = datasets.panel_state  # panel props include the datasets (plan §2.1)

SESSION_KEY = "project_id"

# Allowed payload fields per action: name -> type. Unknown fields are ignored.
FIELDS: dict[str, dict[str, type | tuple[type, ...]]] = {
    "nb_add_cell": {"version": int, "after_id": (str, type(None)), "type": str},
    "nb_update_cell": {"version": int, "cell_id": str, "source": str},
    "nb_delete_cell": {"version": int, "cell_id": str},
    "nb_move_cell": {"version": int, "cell_id": str, "direction": str},
    "nb_reorder_cell": {"version": int, "cell_id": str, "before_id": (str, type(None))},
    "nb_duplicate_cell": {"version": int, "cell_id": str},
    "nb_clear_cell_outputs": {"version": int, "cell_id": str},
    "nb_run_cell": {"version": int, "cell_id": str, "source": str},
    "nb_run_all": {"version": int},
    "nb_interrupt": {"version": int},
    "nb_restart": {"version": int},
    "nb_clear_outputs": {"version": int},
    "nb_list_projects": {},
    "nb_switch_project": {"project_id": str},
    "nb_create_project": {"name": str},
    "ds_delete": {"dataset_id": str},  # NB-3: confirmed in the panel first (A7)
    "ds_cancel": {"dataset_id": str},  # NB-3: stop a running or queued download
}
OPTIONAL = {("nb_add_cell", "after_id"), ("nb_add_cell", "type"), ("nb_reorder_cell", "before_id")}


def session_project(session) -> str:
    """The project of this chat; falls back to the default project."""
    pid = session.get(SESSION_KEY)
    if not pid:
        pid = store.ensure_default_project(service.root).id
        session.set(SESSION_KEY, pid)
    return pid


def read_payload(name: str, payload) -> dict:
    """Check the payload against FIELDS[name]; BAD_PAYLOAD if wrong. Extra fields are dropped."""
    fields = FIELDS.get(name)
    if fields is None or not isinstance(payload, dict):
        raise WorkspaceError(ErrorCode.BAD_PAYLOAD, "Bad request.")
    clean = {}
    for key, kind in fields.items():
        if key not in payload:
            if (name, key) in OPTIONAL:
                continue
            raise WorkspaceError(ErrorCode.BAD_PAYLOAD, f"Missing {key}.")
        value = payload[key]
        # bool is a subclass of int; don't accept True as a version
        if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
            raise WorkspaceError(ErrorCode.BAD_PAYLOAD, f"Bad {key}.")
        clean[key] = value
    return clean


async def switch_project(svc: NotebookService, session, project_id: str):
    """Point this chat at an existing project (the only way to change it)."""
    if project_id not in {p.id for p in store.list_projects(svc.root)}:
        raise WorkspaceError(ErrorCode.NOT_FOUND, "Unknown project.")
    session.set(SESSION_KEY, project_id)
    return await svc.props(project_id)


async def create_and_switch(svc: NotebookService, session, name: str):
    props = await svc.create_project(name)
    session.set(SESSION_KEY, props["project"]["id"])
    return props


async def dispatch(svc: NotebookService, session, name: str, payload) -> dict | list:
    """Run one panel action. Raises WorkspaceError when rejected."""
    p = read_payload(name, payload)
    if name == "nb_switch_project":
        return await switch_project(svc, session, p["project_id"])
    if name == "nb_create_project":
        return await create_and_switch(svc, session, p["name"])
    if name == "nb_list_projects":
        return {"projects": await svc.list_projects(), "current": session_project(session)}
    pid = session_project(session)
    if name == "nb_add_cell":
        return await svc.add_cell(pid, p["version"], p.get("after_id"), p.get("type", "code"))
    if name == "nb_update_cell":
        return await svc.update_cell(pid, p["version"], p["cell_id"], p["source"])
    if name == "nb_delete_cell":
        return await svc.delete_cell(pid, p["version"], p["cell_id"])
    if name == "nb_move_cell":
        return await svc.move_cell(pid, p["version"], p["cell_id"], p["direction"])
    if name == "nb_reorder_cell":
        return await svc.reorder_cell(pid, p["version"], p["cell_id"], p.get("before_id"))
    if name == "nb_duplicate_cell":
        return await svc.duplicate_cell(pid, p["version"], p["cell_id"])
    if name == "nb_clear_cell_outputs":
        return await svc.clear_cell_outputs(pid, p["version"], p["cell_id"])
    if name == "nb_run_cell":
        return await svc.run_cell(pid, p["version"], p["cell_id"], p["source"])
    if name == "nb_run_all":
        return await svc.run_all(pid, p["version"])
    if name == "nb_interrupt":
        return await svc.interrupt(pid)
    if name == "nb_restart":
        return await svc.restart(pid)
    if name == "nb_clear_outputs":
        return await svc.clear_outputs(pid, p["version"])
    if name == "ds_delete":
        await datasets.delete(pid, p["dataset_id"])
        return await svc.props(pid)
    if name == "ds_cancel":
        await datasets.cancel(pid, p["dataset_id"])
        return await svc.props(pid)
    raise WorkspaceError(ErrorCode.BAD_PAYLOAD, "Unknown action.")


async def handle(svc: NotebookService, session, name: str, payload) -> dict | list:
    """dispatch(), but a rejection comes back as the latest props with `error` set."""
    try:
        return await dispatch(svc, session, name, payload)
    except WorkspaceError as err:
        try:
            return await svc.props(session_project(session), err)
        except WorkspaceError:
            return {"error": {"code": err.code, "message": err.message}}
    except Exception:
        log.exception("Notebook action %s failed", name)
        err = WorkspaceError("INTERNAL", "Something went wrong; see the app log.")
        return await svc.props(session_project(session), err)


EDIT_ACTIONS = {
    "nb_add_cell",
    "nb_update_cell",
    "nb_delete_cell",
    "nb_move_cell",
    "nb_reorder_cell",
    "nb_duplicate_cell",
    "nb_clear_cell_outputs",
    "nb_clear_outputs",
}


async def _callback(action: cl.Action):
    if action.name in EDIT_ACTIONS:
        skip_session.set(cl.context.session.id)
    result = await handle(service, cl.user_session, action.name, action.payload)
    if action.name in ("nb_switch_project", "nb_create_project") and "project" in result and not result.get("error"):
        # Move this chat's panel to the new project
        await panels.open(result["project"]["id"], result)
    return result


for _name in FIELDS:
    cl.action_callback(_name)(_callback)


async def open_for_session() -> None:
    """Open this chat's panel on its project (called at chat start)."""
    pid = session_project(cl.user_session)
    await panels.open(pid, await service.props(pid))
    chats.register(cl.context.session)


def close_for_session() -> None:
    session_id = cl.context.session.id
    panels.unregister(session_id)
    chats.unregister(session_id)
    datasets.drop_notes(session_id)
