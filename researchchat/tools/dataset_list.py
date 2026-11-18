"""dataset_list tool: the project's datasets with status, progress and paths."""

import json

import chainlit as cl

from researchchat.workspace.datasets.service import human_size

DEFINITION = {
    "type": "function",
    "function": {
        "name": "dataset_list",
        "description": (
            "List the datasets in the user's project: id, name, status (queued, "
            "downloading, ready, failed, missing), progress, size, licence, what each "
            "one holds (catalog description, column names or a description you saved), "
            "the /work/datasets/... file paths and load_code to use in notebook code. "
            "Data files the project's own code saved are listed too, as created in this "
            "project, with their /work/<file> path. Call this first whenever the user "
            "wants data, before dataset_search, dataset_download or writing a data file "
            "with notebook_run: the project may already have it."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

REUSE_RULES = (
    "You may read any of these without asking the user. "
    "Before you search, download or write data, check whether one of these is what the user wants. "
    "Judge by what the user asks for and what each dataset is about (description, columns), not by the name alone. "
    "Follow these steps in order:\n"
    "1. A dataset marked describe \"write\" says nothing about itself, but may be what the user wants: look at its "
    "first rows with notebook_run (use its load_code) and save one line with dataset_describe before you search "
    "or download anything.\n"
    "2. If one matches and is ready, use it: give its path, and its load_code when the user wants to work with it, "
    "instead of making a copy. Don't search or download.\n"
    "3. If several match, name them and ask which one.\n"
    "4. If the match is missing or failed, say it can't be used and ask whether to download it again. Don't "
    "download it until the user says yes, and if they say no, don't fetch another copy instead.\n"
    "5. Make a new copy only when the user asks for one or for a different version."
)
NAME_MAX_CHARS = 120  # per name in a line; longer ones are cut with "…"
TEXT_MAX_CHARS = 300  # per description in a line
PATH_MAX_CHARS = 120  # per path in a chat line; the JSON keeps the exact path for code
ELLIPSIS = "…"


def step_title(args: dict) -> str:
    return "List datasets"


def one_line(text, limit: int) -> str:
    """Printable characters only, on one line, at most `limit` chars: a name or description can't add lines."""
    line = " ".join("".join(c if c.isprintable() else " " for c in str(text)).split())
    return line if len(line) <= limit else line[: limit - 1] + ELLIPSIS


def _about(v: dict) -> list[str]:
    """What the line says the data holds: catalog text, columns, the assistant's note, or that nothing is known."""
    if v.get("description"):
        return [f'"{v["description"]}"']
    if v.get("columns"):
        return ["columns: " + ", ".join(v["columns"])]
    if v.get("assistant_description"):
        return [f'described by the assistant: "{v["assistant_description"]}"']
    if v.get("describe") == "write":
        return ["nothing known"]
    return []


def _created_line(v: dict) -> str:
    """`- Iris.csv · ready · 4.6 KB · created in this project · columns: … · `/work/Iris.csv``."""
    path = one_line(v["path"], PATH_MAX_CHARS)
    parts = [f"- {v['name']}", v["status"], human_size(v["size_bytes"]), "created in this project", *_about(v), f"`{path}`"]
    return " · ".join(parts)


def _downloaded_line(v: dict) -> str:
    status = v["status"]
    if status == "downloading" and v["size_bytes"]:
        status += f" {100 * (v['done_bytes'] or 0) // v['size_bytes']}%"
    shared = f" · also in {v['shared_with']} other project(s)" if v["shared_with"] else ""
    parts = [f"- {v['name']}", status, human_size(v["size_bytes"]), *_about(v), f"`{one_line(v['path'], PATH_MAX_CHARS)}/`"]
    return " · ".join(parts) + shared


LINE_BY_ORIGIN = {"downloaded": _downloaded_line, "created": _created_line}  # one chat line per dataset kind


def _safe_view(v: dict) -> dict:
    """The view with every free text on one capped line, for the chat line and the JSON alike."""
    safe = dict(v, name=one_line(v["name"], NAME_MAX_CHARS))
    for key in ("description", "assistant_description"):
        if safe.get(key):
            safe[key] = one_line(safe[key], TEXT_MAX_CHARS)
    if safe.get("columns"):
        safe["columns"] = [one_line(c, NAME_MAX_CHARS) for c in safe["columns"]]
    return safe


async def run(args: dict, *, svc=None, project_id: str | None = None) -> tuple[str, str]:
    """Return (text shown in the chat step, JSON {"datasets": [DatasetRecordView], "note": reuse rules})."""
    if svc is None or project_id is None:
        from researchchat.workspace import actions

        svc = svc or actions.datasets
        project_id = project_id or actions.session_project(cl.user_session)
    views = [_safe_view(v) for v in svc.list_for_model(project_id)]
    if not views:
        return "No datasets in this project yet.", json.dumps({"datasets": []})
    shown = "\n".join(LINE_BY_ORIGIN[v["origin"]](v) for v in views)
    return shown, json.dumps({"datasets": views, "note": REUSE_RULES})
