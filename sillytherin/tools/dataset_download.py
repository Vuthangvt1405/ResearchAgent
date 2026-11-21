"""dataset_download tool: start a background download into the project.

Quick checks happen here; the transfer runs in the background and the tool
returns at once. Downloads above ask_above_mb show Download / Skip, and a
dataset whose copy in the project failed or is missing shows "Download again?"
first. Unknown arguments are ignored, so {"approved": true} can't skip a prompt.
"""

import json
from typing import TYPE_CHECKING

from sillytherin.chat.current import this_chat
from sillytherin.chat.ports import Choice
from sillytherin.tools.services import (
    ConfirmRetry,
    DatasetDownloader,
    ProjectDatasetLookup,
    UndescribedDatasets,
)
from sillytherin.tools.titles import shorten
from sillytherin.workspace import ErrorCode, WorkspaceError
from sillytherin.workspace.datasets import links
from sillytherin.workspace.datasets.describe import look_first_message
from sillytherin.workspace.datasets.service import REF_PREFIXES, Approve, human_size
from sillytherin.workspace.datasets.sources import DatasetPlan

if TYPE_CHECKING:
    from sillytherin.tools.dataset_describe import ChatLooks

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
            "copy a file elsewhere in /work before changing it. Check dataset_list first: "
            "when the project already has matching data, use it; download a new copy only "
            "when the user asks for one or for a different version."
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
DOWNLOAD_CHOICE = Choice("download", "Download")
DOWNLOAD_OR_SKIP = (DOWNLOAD_CHOICE, Choice("skip", "Skip"))
DOWNLOAD_AGAIN_CHOICE = Choice("download_again", "Download again")
DOWNLOAD_AGAIN_OR_SKIP = (DOWNLOAD_AGAIN_CHOICE, Choice("skip", "Skip"))
MAX_PATTERNS = 20
PATTERN_MAX_CHARS = 200
SOURCE_NAMES = {"huggingface": "Hugging Face", "zenodo": "Zenodo"}


def pasted_links_in_chat() -> frozenset[str]:
    """Links the user pasted in this chat, from the chat's model history."""
    return links.find_pasted_links(this_chat().state.get("history") or [])


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
    question = (
        f"The assistant wants to download **{plan.name}** from {SOURCE_NAMES.get(plan.source, plan.source)}: "
        f"{count:,} file{'s' if count != 1 else ''}, **{human_size(download_bytes)}**.\n\n"
        f"Licence: {plan.license or 'not stated'} · {plan.url}"
    )
    answer = await this_chat().asker.ask_choice(question, DOWNLOAD_OR_SKIP, APPROVAL_TIMEOUT_SECONDS)
    return answer == DOWNLOAD_CHOICE.id


BROKEN_STATUSES = ("failed", "missing")  # a copy the project can't use; downloading it again needs the user's yes


async def ask_retry(name: str, reason: str | None) -> bool:
    """Download again / Skip for a copy that can't be used; False on Skip or timeout."""
    why = f" ({reason})" if reason else ""
    question = f"This project's copy of **{name}** can't be used{why}. Download it again?"
    answer = await this_chat().asker.ask_choice(question, DOWNLOAD_AGAIN_OR_SKIP, APPROVAL_TIMEOUT_SECONDS)
    return answer == DOWNLOAD_AGAIN_CHOICE.id


def undescribed_not_looked_at(
    svc: UndescribedDatasets, project_id: str, session_id: str, ref: str, looked: "ChatLooks | None" = None
) -> list[dict]:
    """Ready rows with describe "write" the assistant hasn't looked at in this chat, so no download yet; none for a pasted link."""
    from sillytherin.tools.dataset_describe import looked as chat_looks

    try:
        if links.parse_dataset_ref(ref)[0] == links.LINK_SOURCE:
            return []  # the user pasted it: their explicit wish
        views = svc.needs_description(project_id)
    except WorkspaceError:
        return []  # the request reports a bad ref or project
    seen = looked or chat_looks
    return [v for v in views if not seen.has_looked(session_id, project_id, v["dataset_id"])]


def broken_copy(svc: ProjectDatasetLookup, project_id: str, ref: str) -> dict | None:
    """The project's own copy of this catalog entry when it is failed or missing; None otherwise (links too)."""
    try:
        source, source_id = links.parse_dataset_ref(ref)
    except WorkspaceError:
        return None  # the request reports the bad ref
    prefix = REF_PREFIXES.get(source)
    own = svc.project_refs(project_id).get(f"{prefix}:{source_id}") if prefix else None
    return own if own and own["status"] in BROKEN_STATUSES else None


def download_size_text(download_bytes: int) -> str:
    """The size to download, or "size unknown" when a linked website sent none (a download is never 0 B)."""
    return human_size(download_bytes) if download_bytes else "size unknown"


def error_json(err: WorkspaceError) -> str:
    """A WorkspaceError as JSON for the model, with its structured details."""
    return json.dumps({"error": err.code, "message": err.message, **(err.details or {})})


async def run(
    args: dict,
    *,
    svc: DatasetDownloader | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
    approve: Approve | None = None,
    pasted_links: frozenset[str] | None = None,
    confirm_retry: ConfirmRetry | None = None,
    looked: "ChatLooks | None" = None,
) -> tuple[str, str]:
    """Return (text shown in the chat step, JSON DownloadStarted for the model).

    svc / project_id / session_id / approve / pasted_links default to
    actions.datasets, this chat's project, this chat's id, the chat
    prompt and the links in the user's messages; tests pass fakes (confirm_retry:
    the "Download again?" prompt).
    """
    ref, files, update = read_args(args)
    if svc is None or project_id is None or session_id is None:
        from sillytherin.workspace import actions

        svc = svc or actions.datasets
        chat = this_chat().state
        project_id = project_id or actions.session_project(chat)
        session_id = session_id or chat.chat_id
        if pasted_links is None:
            pasted_links = pasted_links_in_chat()
    not_looked_at = undescribed_not_looked_at(svc, project_id, session_id, ref, looked)
    if not_looked_at:
        error = WorkspaceError(
            ErrorCode.LOOK_FIRST,
            look_first_message([v["name"] for v in not_looked_at]),
            {"datasets": [v["dataset_id"] for v in not_looked_at]},
        )
        raise ValueError(error_json(error))
    broken = broken_copy(svc, project_id, ref)
    if broken and not await (confirm_retry or ask_retry)(broken["name"], broken.get("error")):
        declined = WorkspaceError(
            ErrorCode.DECLINED,
            "The user chose not to download it again. Don't download it or any other copy now; tell the user "
            "the project's copy can't be used and stop.",
        )
        return f"Skipped: **{broken['name']}** was not downloaded again.", error_json(declined)
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
