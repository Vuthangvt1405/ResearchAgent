"""dataset_describe tool: save one line about what a dataset holds, when it says nothing itself.

Rows marked describe "write" in dataset_list are saved at once. Every file in
the project may be read without asking the user, whoever added it.
"""

import json

from sillytherin.chat.current import this_chat
from sillytherin.tools.dataset_download import error_json
from sillytherin.tools.services import DatasetDescriber
from sillytherin.workspace import ErrorCode, WorkspaceError

DEFINITION = {
    "type": "function",
    "function": {
        "name": "dataset_describe",
        "description": (
            "Save a one-line description of a dataset in the user's project that says "
            "nothing about itself (dataset_list marks it with describe): look at its first "
            "rows with notebook_run, then call this with dataset_id and description."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string", "description": "Id from dataset_list."},
                "description": {
                    "type": "string",
                    "description": "What the data holds, in one line (at most 300 characters). Leave out to ask the user.",
                },
            },
            "required": ["dataset_id"],
        },
    },
}


def step_title(args: dict) -> str:
    return "Describe dataset"


class ChatLooks:
    """Undescribed datasets the assistant ran code on, per chat (memory only, forgotten when the chat ends)."""

    def __init__(self) -> None:
        self._looked: dict[str, set[tuple[str, str]]] = {}  # session_id -> {(project_id, dataset_id)}

    def remember(self, session_id: str, project_id: str, dataset_id: str) -> None:
        self._looked.setdefault(session_id, set()).add((project_id, dataset_id))

    def has_looked(self, session_id: str, project_id: str, dataset_id: str) -> bool:
        return (project_id, dataset_id) in self._looked.get(session_id, set())

    def forget(self, session_id: str) -> None:
        """The chat ended: what the assistant looked at in it no longer counts."""
        self._looked.pop(session_id, None)


looked = ChatLooks()  # undescribed datasets the assistant looked at (notebook_run), per chat; lets downloads go


async def run(
    args: dict,
    *,
    svc: DatasetDescriber | None = None,
    project_id: str | None = None,
) -> tuple[str, str]:
    """Return (text shown in the chat step, JSON for the model).

    Only dataset_id → what to do next. With description → save it as
    {saved, description}. svc / project_id default to the app's service and
    this chat's project; tests pass their own.
    """
    dataset_id = args.get("dataset_id")
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise ValueError("No dataset_id given. Use an id from dataset_list.")
    description = args.get("description")  # any other argument is ignored
    if svc is None or project_id is None:
        from sillytherin.workspace import actions

        svc = svc or actions.datasets
        project_id = project_id or actions.session_project(this_chat().state)
    try:
        view = svc.view_for_model(project_id, dataset_id.strip())
        if view["describe"] is None:
            raise WorkspaceError(ErrorCode.NOT_NEEDED, "This dataset already says what it holds, or isn't ready.")
        if description is None:
            return f"Ready to note what **{view['name']}** holds.", json.dumps({"allowed": True, "next": NEXT_STEP})
        saved = await svc.save_description(project_id, view["dataset_id"], description)
    except WorkspaceError as e:
        raise ValueError(error_json(e)) from e
    text = saved["assistant_description"]
    return f"Noted what **{view['name']}** holds: {text}", json.dumps({"saved": view["dataset_id"], "description": text})


NEXT_STEP = "Look at its first rows with notebook_run, then call dataset_describe again with a one-line description."
