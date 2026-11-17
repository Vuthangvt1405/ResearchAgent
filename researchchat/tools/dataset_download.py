"""dataset_download tool: start a background download into the project.

Quick checks happen here; the transfer runs in the background and the tool
returns at once. Downloads above ask_above_mb show Download / Skip.
Unknown arguments are ignored, so {"approved": true} can't skip the prompt.
"""

import json

import chainlit as cl

from researchchat.tools.titles import shorten
from researchchat.workspace import ErrorCode, WorkspaceError
from researchchat.workspace.datasets import links
from researchchat.workspace.datasets.service import human_size
from researchchat.workspace.datasets.sources import DatasetPlan

DEFINITION = {
    "type": "function",
    "function": {
        "name": "dataset_download",
        "description": (
            "Download a dataset found with dataset_search into the user's project, "
            "in the background. Pass its `ref`, or a https link to a data file that "
            "the user pasted into the chat. Never pass a link from anywhere else: "
            "show it to the user and ask them to paste it if they want it. A link "
            "has no licence information; don't state one. Returns at once with the dataset id "
            "and the /work/datasets/<id>/ paths the files will have; you'll be told "
            "when it's ready, so don't read the files before then. Use `files` "
            "(names or globs like \"*.csv\") for big datasets. Set `update` only "
            "when the user asks to update to the newest version. Data other "
            "projects already have is ready at once. Dataset files are read-only: "
            "copy a file elsewhere in /work before changing it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": (
                        "Dataset ref from dataset_search, e.g. hf:org/name or zenodo:7395559, "
                        "or a file link the user pasted, e.g. https://example.org/data/iris.csv."
                    ),
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Only these files: names or glob patterns (at most 20).",
                },
                "update": {
                    "type": "boolean",
                    "description": "Fetch the newest version. Only when the user asks for it.",
                },
            },
            "required": ["ref"],
        },
    },
}

APPROVAL_TIMEOUT_SECONDS = 120
MAX_PATTERNS = 20
PATTERN_MAX_CHARS = 200
SOURCE_NAMES = {"huggingface": "Hugging Face", "zenodo": "Zenodo"}


def pasted_links_in_chat() -> frozenset[str]:
    """Links the user pasted in this chat, from the model history of the Chainlit session."""
    return links.find_pasted_links(cl.user_session.get("history") or [])


def step_title(args: dict) -> str:
    ref = args.get("ref")
    return f"Download dataset: {shorten(ref)}" if isinstance(ref, str) and ref.strip() else "Download dataset"


def read_args(args: dict) -> tuple[str, list[str] | None, bool]:
    """(ref, files, update), or ValueError before the service is called.

    Unknown keys are ignored, so {"approved": true} changes nothing.
    """
    ref = args.get("ref")
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("No dataset ref given. Pass the `ref` from a dataset_search result.")
    files = args.get("files")
    if files is not None:
        if not isinstance(files, list) or not files:
            raise ValueError("`files` must be a list of file names or patterns like \"*.csv\".")
        if len(files) > MAX_PATTERNS:
            raise ValueError(f"`files` can have at most {MAX_PATTERNS} names or patterns.")
        for pattern in files:
            if (
                not isinstance(pattern, str)
                or not 1 <= len(pattern) <= PATTERN_MAX_CHARS
                or not pattern.strip()
                or pattern.startswith("/")
                or "\\" in pattern
                or "\x00" in pattern
                or ".." in pattern.split("/")
            ):
                raise ValueError(f"Bad file name or pattern in `files`: {str(pattern)[:60]!r}")
    update = args.get("update", False)
    if update is None:
        update = False
    if not isinstance(update, bool):
        raise ValueError("`update` must be true or false.")
    return ref.strip(), files, update


async def ask_approval(plan: DatasetPlan, download_bytes: int) -> bool:
    """Name, file count, size and licence with Download / Skip; False on Skip or timeout."""
    count = len(plan.files)
    ask = cl.AskActionMessage(
        content=(
            f"The assistant wants to download **{plan.name}** from {SOURCE_NAMES.get(plan.source, plan.source)}: "
            f"{count:,} file{'s' if count != 1 else ''}, **{human_size(download_bytes)}**.\n\n"
            f"Licence: {plan.license or 'not stated'} · {plan.url}"
        ),
        actions=[
            cl.Action(name="download", payload={"download": True}, label="Download"),
            cl.Action(name="skip", payload={"download": False}, label="Skip"),
        ],
        timeout=APPROVAL_TIMEOUT_SECONDS,
    )
    ask.parent_id = None  # don't hide the question inside the collapsed tool group
    answer = await ask.send()
    return bool(answer and answer.get("payload", {}).get("download"))


def download_size_text(download_bytes: int) -> str:
    """The size to download, or "size unknown" when a linked website sent none (a download is never 0 B)."""
    return human_size(download_bytes) if download_bytes else "size unknown"


def error_json(err: WorkspaceError) -> str:
    """A WorkspaceError as JSON for the model, with its structured details."""
    return json.dumps({"error": err.code, "message": err.message, **(err.details or {})})


async def run(
    args: dict,
    *,
    svc=None,
    project_id: str | None = None,
    session_id: str | None = None,
    approve=None,
    pasted_links: frozenset[str] | None = None,
) -> tuple[str, str]:
    """Return (text shown in the chat step, JSON DownloadStarted for the model).

    svc / project_id / session_id / approve / pasted_links default to
    actions.datasets, this chat's project, cl.context.session.id, the chat
    prompt and the links in the user's messages; tests pass fakes.
    """
    ref, files, update = read_args(args)
    if svc is None or project_id is None or session_id is None:
        from researchchat.workspace import actions

        svc = svc or actions.datasets
        project_id = project_id or actions.session_project(cl.user_session)
        session_id = session_id or cl.context.session.id
        if pasted_links is None:
            pasted_links = pasted_links_in_chat()
    try:
        started = await svc.request(
            project_id, session_id, ref, files, update, approve=approve or ask_approval,
            pasted_links=pasted_links or frozenset(),
        )
    except WorkspaceError as e:
        if e.code == ErrorCode.DECLINED:
            return "Skipped: the user chose not to download it.", error_json(e)
        raise ValueError(error_json(e)) from e
    if started["from_pool"] and started["already_downloaded"]:
        shown = f"Ready from the shared pool, nothing downloaded: `{started['path']}/`"
    elif started["already_downloaded"]:
        shown = f"Already downloaded: `{started['path']}/`"
    elif started["status"] == "queued":
        shown = f"Queued ({download_size_text(started['download_bytes'])}), {started['position_in_queue']} ahead → `{started['path']}/`"
    else:
        shown = f"Downloading in the background ({download_size_text(started['download_bytes'])}) → `{started['path']}/`"
    return shown, json.dumps(started)
