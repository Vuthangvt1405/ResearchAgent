"""dataset_list tool: the project's datasets with status, progress and paths (NB-3 AC24)."""

import json

import chainlit as cl

from researchchat.workspace.dataset_service import human_size

DEFINITION = {
    "type": "function",
    "function": {
        "name": "dataset_list",
        "description": (
            "List the datasets in the user's project: id, name, status (queued, "
            "downloading, ready, failed, missing), progress, size, licence and the "
            "/work/datasets/... file paths to use in notebook code."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}


def step_title(args: dict) -> str:
    return "List datasets"


def _line(v: dict) -> str:
    status = v["status"]
    if status == "downloading" and v["size_bytes"]:
        status += f" {100 * (v['done_bytes'] or 0) // v['size_bytes']}%"
    shared = f" · also in {v['shared_with']} other project(s)" if v["shared_with"] else ""
    return f"- {v['name']} · {status} · {human_size(v['size_bytes'])} · `{v['path']}/`{shared}"


async def run(args: dict, *, svc=None, project_id: str | None = None) -> tuple[str, str]:
    """Return (text shown in the chat step, JSON list of DatasetRecordView)."""
    if svc is None or project_id is None:
        from researchchat.workspace import actions

        svc = svc or actions.datasets
        project_id = project_id or actions.session_project(cl.user_session)
    views = svc.list_for_model(project_id)
    shown = "\n".join(_line(v) for v in views) or "No datasets in this project yet."
    return shown, json.dumps(views)
