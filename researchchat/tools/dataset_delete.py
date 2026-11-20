"""dataset_delete tool: delete one dataset, only after the user agrees.

Every model delete shows Delete / Keep with the name and the space it frees.
"""

import json

from researchchat.chat.current import this_chat
from researchchat.chat.ports import Choice
from researchchat.tools.dataset_download import error_json
from researchchat.tools.services import ApproveDelete, DatasetDeleter
from researchchat.workspace import ErrorCode, WorkspaceError
from researchchat.workspace.datasets.service import human_size

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
DELETE_CHOICE = Choice("delete", "Delete")
DELETE_OR_KEEP = (DELETE_CHOICE, Choice("keep", "Keep"))


def step_title(args: dict) -> str:
    return "Delete dataset"


def approval_text(name: str, frees_bytes: int, shared_with: int) -> str:
    """The Delete / Keep question; a dataset other projects use frees nothing here."""
    text = f"The assistant wants to delete the dataset **{name}** from this project, freeing **{human_size(frees_bytes)}**."
    if shared_with:
        others = "1 other project" if shared_with == 1 else f"{shared_with} other projects"
        text += f" Also used by {others}: they keep it."
    return text


async def ask_approval(name: str, frees_bytes: int, shared_with: int) -> bool:
    """Delete / Keep in the chat; False on Keep or timeout."""
    question = approval_text(name, frees_bytes, shared_with)
    answer = await this_chat().asker.ask_choice(question, DELETE_OR_KEEP, APPROVAL_TIMEOUT_SECONDS)
    return answer == DELETE_CHOICE.id


async def run(
    args: dict, *, svc: DatasetDeleter | None = None, project_id: str | None = None,
    approve: ApproveDelete | None = None,
) -> tuple[str, str]:
    """Return (text shown in the chat step, JSON {deleted, freed_bytes, still_used_by})."""
    dataset_id = args.get("dataset_id")
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise ValueError("No dataset_id given. Use an id from dataset_list.")
    if svc is None or project_id is None:
        from researchchat.workspace import actions

        svc = svc or actions.datasets
        project_id = project_id or actions.session_project(this_chat().state)
    try:
        view = svc.describe(project_id, dataset_id.strip())
        frees_bytes = 0 if view["shared_with"] else view["size_bytes"]
        if not await (approve or ask_approval)(view["name"], frees_bytes, view["shared_with"]):
            declined = WorkspaceError(ErrorCode.DECLINED, "The user chose to keep this dataset.")
            return f"Kept **{view['name']}**.", error_json(declined)
        result = await svc.delete(project_id, view["dataset_id"])
    except WorkspaceError as e:
        raise ValueError(error_json(e)) from e
    shown = f"Deleted **{view['name']}**, freed {human_size(result['freed_bytes'])}."
    if result["still_used_by"]:
        shown += " Other projects still use it, so its files stay."
    return shown, json.dumps(result)
