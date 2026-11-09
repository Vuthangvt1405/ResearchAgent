"""notebook_run tool: run Python in the project's notebook.

Safe code runs at once (AC10). Risky code is shown in the chat with the
reasons and Run / Skip buttons, and runs only on Run (AC11).
"""

import chainlit as cl

from researchchat.config import MODEL_AUTO_RUN, RISKY_CODE_NEEDS_APPROVAL
from researchchat.workspace import WorkspaceError, risk

DEFINITION = {
    "type": "function",
    "function": {
        "name": "notebook_run",
        "description": (
            "Run Python code in the user's project notebook (a Jupyter kernel "
            "with numpy, pandas and matplotlib; files live in the working "
            "folder). Variables persist between runs. The code is added as a "
            "new cell. Returns the printed output, the last value or the error."
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


def step_title(args: dict) -> str:
    return "Notebook: run code"


async def ask_approval(code: str, reasons: list[str]) -> bool:
    """Show code + reasons with Run / Skip; False on Skip or timeout."""
    why = "\n".join(f"- {r}" for r in reasons) or "- automatic running is turned off"
    ask = cl.AskActionMessage(
        content=f"The assistant wants to run this code:\n\n```python\n{code}\n```\n\n**Asking because it:**\n{why}",
        actions=[
            cl.Action(name="run", payload={"run": True}, label="Run"),
            cl.Action(name="skip", payload={"run": False}, label="Skip"),
        ],
        timeout=APPROVAL_TIMEOUT_SECONDS,
    )
    # Chainlit nests a message under the step it's created in, and the tool
    # steps live in a collapsed group, so the question would be hidden.
    ask.parent_id = None
    answer = await ask.send()
    return bool(answer and answer.get("payload", {}).get("run"))


async def run(args: dict, *, svc=None, project_id: str | None = None, approve=None) -> tuple[str, str]:
    """Return (text shown in the chat step, result sent to the model).

    svc / project_id / approve default to the app's service, this chat's
    project and the chat prompt; tests pass their own.
    """
    code = str(args.get("code") or "")
    if not code.strip():
        raise ValueError("No code given.")
    if svc is None or project_id is None:
        from researchchat.workspace import actions

        svc = svc or actions.service
        project_id = project_id or actions.session_project(cl.user_session)
    approve = approve or ask_approval

    reasons = risk.check(code)
    needs_ok = (reasons and RISKY_CODE_NEEDS_APPROVAL) or not MODEL_AUTO_RUN
    if needs_ok and not await approve(code, reasons):
        return f"```python\n{code}\n```\n\nSkipped.", DECLINED
    try:
        result = await svc.run_for_model(project_id, code)
    except WorkspaceError as e:
        raise ValueError(e.message) from e
    return f"```python\n{code}\n```\n\n```\n{result}\n```", result
