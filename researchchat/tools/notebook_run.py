"""notebook_run tool: run Python in the project's notebook.

Safe code runs at once. Risky code is shown in the chat with the
reasons and Run / Skip buttons, and runs only on Run. Any file in the project
may be read without asking the user, whoever added it.
"""

from typing import TYPE_CHECKING

from researchchat.chat.current import this_chat
from researchchat.chat.ports import Choice
from researchchat.config import MODEL_AUTO_RUN, RISKY_CODE_NEEDS_APPROVAL
from researchchat.tools.services import ApproveRun, NotebookRunner, UndescribedDatasets
from researchchat.workspace import WorkspaceError, risk

if TYPE_CHECKING:
    from researchchat.tools.dataset_describe import ChatLooks

DEFINITION = {
    "type": "function",
    "function": {
        "name": "notebook_run",
        "description": (
            "Run Python code in the user's project notebook (a Jupyter kernel "
            "with numpy, pandas and matplotlib; files live in the working "
            "folder). Variables persist between runs. The code is added as a "
            "new cell. Returns the printed output, the last value or the error. "
            "Before writing a data file, check dataset_list: when the project already has "
            "matching data, load it from its path; write a new copy only when the user asks for one."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to run."}
            },
            "required": ["code"],
        },
    },
}

APPROVAL_TIMEOUT_SECONDS = 120
DECLINED = "User declined to run this code."


def undescribed_named_in(code: str, views: list[dict]) -> list[dict]:
    """Rows with describe "write" whose /work path or name appears in the code (any case)."""
    lowered = code.lower()
    return [v for v in views if v.get("describe") == "write" and (v["path"].lower() in lowered or v["name"].lower() in lowered)]


def _remember_looks(
    code: str, datasets: UndescribedDatasets, project_id: str, session_id: str, looked: "ChatLooks | None"
) -> None:
    """The assistant looked at these undescribed datasets in this chat: downloads may go ahead."""
    from researchchat.tools.dataset_describe import looked as chat_looks

    try:
        views = datasets.needs_description(project_id)
    except WorkspaceError:
        return
    for view in undescribed_named_in(code, views):
        (looked or chat_looks).remember(session_id, project_id, view["dataset_id"])


RUN_CHOICE = Choice("run", "Run")
RUN_OR_SKIP = (RUN_CHOICE, Choice("skip", "Skip"))


def step_title(args: dict) -> str:
    return "Notebook: run code"


async def ask_approval(code: str, reasons: list[str]) -> bool:
    """Show code + reasons with Run / Skip; False on Skip or timeout."""
    why = "\n".join(f"- {r}" for r in reasons) or "- automatic running is turned off"
    question = f"The assistant wants to run this code:\n\n```python\n{code}\n```\n\n**Asking because it:**\n{why}"
    answer = await this_chat().asker.ask_choice(question, RUN_OR_SKIP, APPROVAL_TIMEOUT_SECONDS)
    return answer == RUN_CHOICE.id


async def run(
    args: dict,
    *,
    svc: NotebookRunner | None = None,
    project_id: str | None = None,
    approve: ApproveRun | None = None,
    datasets: UndescribedDatasets | None = None,
    session_id: str | None = None,
    looked: "ChatLooks | None" = None,
) -> tuple[str, str]:
    """Return (text shown in the chat step, result sent to the model).

    svc / project_id / approve / datasets / session_id / looked default to the
    app's services, this chat, its prompt and the chat's looks; tests pass their
    own (no `datasets`: looks aren't recorded).
    """
    code = str(args.get("code") or "")
    if not code.strip():
        raise ValueError("No code given.")
    if svc is None or project_id is None:
        from researchchat.workspace import actions

        svc = svc or actions.service
        chat = this_chat().state
        project_id = project_id or actions.session_project(chat)
        datasets = datasets or actions.datasets
        session_id = session_id or chat.chat_id
    approve = approve or ask_approval

    reasons = risk.check(code)
    needs_ok = (reasons and RISKY_CODE_NEEDS_APPROVAL) or not MODEL_AUTO_RUN
    if needs_ok and not await approve(code, reasons):
        return f"```python\n{code}\n```\n\nSkipped.", DECLINED
    try:
        result = await svc.run_for_model(project_id, code)
    except WorkspaceError as e:
        raise ValueError(e.message) from e
    if datasets is not None:
        _remember_looks(code, datasets, project_id, session_id or "", looked)
    return f"```python\n{code}\n```\n\n```\n{result}\n```", result
