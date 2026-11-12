"""dataset_delete tool: delete one dataset, only after the user agrees (NB-3 AC26).

Every model delete shows Delete / Keep with the name and the space it frees.
"""

import json

import chainlit as cl

from researchchat.tools.dataset_download import error_json
from researchchat.workspace import ErrorCode, WorkspaceError
from researchchat.workspace.dataset_service import human_size

DEFINITION = {
    "type": "function",
    "function": {
        "name": "dataset_delete",
        "description": (
            "Delete a dataset from the user's project to free disk space. The user "
            "is always asked first. Pass the dataset_id from dataset_list."
        ),
        "parameters": {
            "type": "object",
            "properties": {"dataset_id": {"type": "string", "description": "Id from dataset_list."}},
            "required": ["dataset_id"],
        },
    },
}

APPROVAL_TIMEOUT_SECONDS = 120


def step_title(args: dict) -> str:
    return "Delete dataset"


async def ask_approval(name: str, size_bytes: int) -> bool:
    """Delete / Keep in the chat; False on Keep or timeout."""
    ask = cl.AskActionMessage(
        content=f"The assistant wants to delete the dataset **{name}** from this project, freeing **{human_size(size_bytes)}**.",
        actions=[
            cl.Action(name="delete", payload={"delete": True}, label="Delete"),
            cl.Action(name="keep", payload={"delete": False}, label="Keep"),
        ],
        timeout=APPROVAL_TIMEOUT_SECONDS,
    )
    ask.parent_id = None  # don't hide the question inside the collapsed tool group
    answer = await ask.send()
    return bool(answer and answer.get("payload", {}).get("delete"))


async def run(
    args: dict, *, svc=None, project_id: str | None = None, approve=None
) -> tuple[str, str]:
    """Return (text shown in the chat step, JSON {deleted, freed_bytes})."""
    dataset_id = args.get("dataset_id")
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise ValueError("No dataset_id given. Use an id from dataset_list.")
    if svc is None or project_id is None:
        from researchchat.workspace import actions

        svc = svc or actions.datasets
        project_id = project_id or actions.session_project(cl.user_session)
    try:
        view = svc.describe(project_id, dataset_id.strip())
        if not await (approve or ask_approval)(view["name"], view["size_bytes"]):
            declined = WorkspaceError(ErrorCode.DECLINED, "The user chose to keep this dataset.")
            return f"Kept **{view['name']}**.", error_json(declined)
        result = await svc.delete(project_id, view["dataset_id"])
    except WorkspaceError as e:
        raise ValueError(error_json(e)) from e
    return f"Deleted **{view['name']}**, freed {human_size(result['freed_bytes'])}.", json.dumps(result)
