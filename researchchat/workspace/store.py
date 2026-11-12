"""Projects and notebooks on disk.

workspaces/<project_id>/
    project.json     {"name": ..., "created_at": ...}
    notebook.ipynb   nbformat 4.5; metadata.researchchat.version = int
    files/           mounted into the kernel container as /work
"""

import json
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import nbformat
from nbformat import NotebookNode

from researchchat.config import WORKSPACES_DIR
from researchchat.workspace import ErrorCode, WorkspaceError

PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
PROJECT_ID_MAX = 40
PROJECT_NAME_MAX = 80
DEFAULT_PROJECT_ID = "default"
DEFAULT_PROJECT_NAME = "Default"
FALLBACK_ID = "project"  # for names with no Latin letters or digits
MAX_SOURCE_BYTES = 100 * 1024

PROJECT_FILE = "project.json"
NOTEBOOK_FILE = "notebook.ipynb"
FILES_DIR = "files"

CellType = Literal["code", "markdown"]
Direction = Literal["up", "down"]
CELL_TYPES = ("code", "markdown")
DIRECTIONS = ("up", "down")


@dataclass
class Project:
    id: str  # safe slug, also the folder name
    name: str  # display name, any text (1-80 chars)
    created_at: str  # ISO 8601, UTC


# ---- projects ----------------------------------------------------------------


def slugify(name: str) -> str:
    """Turn a display name into a project id: "Tokyo Housing!!" -> "tokyo-housing"."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    slug = slug[:PROJECT_ID_MAX].strip("-")
    return slug or FALLBACK_ID


def project_dir(project_id: str, root: Path = WORKSPACES_DIR) -> Path:
    """Folder of a project, guaranteed to be inside `root`."""
    if not isinstance(project_id, str) or not PROJECT_ID_RE.match(project_id):
        raise WorkspaceError(ErrorCode.NOT_FOUND, "Unknown project.")
    base = Path(root).resolve()
    folder = (base / project_id).resolve()
    if folder.parent != base:
        raise WorkspaceError(ErrorCode.NOT_FOUND, "Unknown project.")
    return folder


def _unique_id(base: str, root: Path) -> str:
    if not (Path(root) / base).exists():
        return base
    n = 2
    while True:
        suffix = f"-{n}"
        candidate = base[: PROJECT_ID_MAX - len(suffix)].rstrip("-") + suffix
        if not (Path(root) / candidate).exists():
            return candidate
        n += 1


def _new_notebook() -> NotebookNode:
    nb = nbformat.v4.new_notebook()
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    nb.metadata["researchchat"] = {"version": 0}
    return nb


def create_project(name: str, root: Path = WORKSPACES_DIR, project_id: str | None = None) -> Project:
    """Create the folder, project.json, an empty notebook and files/."""
    name = (name or "").strip()
    if not name or len(name) > PROJECT_NAME_MAX:
        raise WorkspaceError(ErrorCode.BAD_NAME, f"Project names must be 1-{PROJECT_NAME_MAX} characters.")
    Path(root).mkdir(parents=True, exist_ok=True)
    pid = project_id or _unique_id(slugify(name), root)
    folder = project_dir(pid, root)
    folder.mkdir(exist_ok=False)  # never reuse an existing folder
    (folder / FILES_DIR).mkdir()
    project = Project(pid, name, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    (folder / PROJECT_FILE).write_text(
        json.dumps({"name": project.name, "created_at": project.created_at}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    save_notebook(pid, _new_notebook(), root)
    return project


def ensure_default_project(root: Path = WORKSPACES_DIR) -> Project:
    """Create the `default` project on first start; return the project to open."""
    projects = list_projects(root)
    if not projects:
        return create_project(DEFAULT_PROJECT_NAME, root, project_id=DEFAULT_PROJECT_ID)
    return next((p for p in projects if p.id == DEFAULT_PROJECT_ID), projects[0])


def list_projects(root: Path = WORKSPACES_DIR) -> list[Project]:
    """All projects, for the project bar, sorted by name."""
    if not Path(root).is_dir():
        return []
    projects = []
    for folder in Path(root).iterdir():
        if folder.is_dir() and PROJECT_ID_RE.match(folder.name) and (folder / PROJECT_FILE).is_file():
            projects.append(get_project(folder.name, root))
    return sorted(projects, key=lambda p: (p.name.lower(), p.id))


def get_project(project_id: str, root: Path = WORKSPACES_DIR) -> Project:
    """One project; NOT_FOUND if it doesn't exist."""
    path = project_dir(project_id, root) / PROJECT_FILE
    if not path.is_file():
        raise WorkspaceError(ErrorCode.NOT_FOUND, "Unknown project.")
    data = json.loads(path.read_text(encoding="utf-8"))
    return Project(project_id, str(data.get("name") or project_id), str(data.get("created_at", "")))


# ---- notebook file ---------------------------------------------------------------


def load_notebook(project_id: str, root: Path = WORKSPACES_DIR) -> NotebookNode:
    """Read notebook.ipynb."""
    path = project_dir(project_id, root) / NOTEBOOK_FILE
    if not path.is_file():
        raise WorkspaceError(ErrorCode.NOT_FOUND, "Unknown project.")
    with open(path, encoding="utf-8") as f:
        return nbformat.read(f, as_version=4)


def save_notebook(project_id: str, nb: NotebookNode, root: Path = WORKSPACES_DIR) -> None:
    """Write notebook.ipynb atomically: a temp file, then os.replace."""
    nbformat.validate(nb)
    path = project_dir(project_id, root) / NOTEBOOK_FILE
    tmp = path.with_name(NOTEBOOK_FILE + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            nbformat.write(nb, f)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def get_version(nb: NotebookNode) -> int:
    """metadata.researchchat.version (0 for a new notebook)."""
    return int(nb.metadata.get("researchchat", {}).get("version", 0))


def bump_version(nb: NotebookNode) -> int:
    """Add 1 to the version and return it."""
    meta = nb.metadata.setdefault("researchchat", {})
    meta["version"] = get_version(nb) + 1
    return meta["version"]


# ---- cells -------------------------------------------------------------------------


def find_cell(nb: NotebookNode, cell_id: str) -> NotebookNode:
    """The cell with this id; NOT_FOUND otherwise."""
    for cell in nb.cells:
        if cell.get("id") == cell_id:
            return cell
    raise WorkspaceError(ErrorCode.NOT_FOUND, "That cell no longer exists.")


def _index(nb: NotebookNode, cell_id: str) -> int:
    return nb.cells.index(find_cell(nb, cell_id))


def add_cell(nb: NotebookNode, cell_type: CellType, after_id: str | None) -> NotebookNode:
    """Insert an empty cell after `after_id`, or at the end; return it."""
    if cell_type not in CELL_TYPES:
        raise WorkspaceError(ErrorCode.BAD_TYPE, "Cells are code or notes.")
    position = len(nb.cells) if after_id is None else _index(nb, after_id) + 1
    cell = nbformat.v4.new_code_cell("") if cell_type == "code" else nbformat.v4.new_markdown_cell("")
    nb.cells.insert(position, cell)
    return cell


def update_cell(nb: NotebookNode, cell_id: str, source: str) -> None:
    """Replace a cell's source."""
    cell = find_cell(nb, cell_id)
    if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise WorkspaceError(ErrorCode.TOO_LARGE, "A cell can hold at most 100 KB.")
    cell.source = source


def delete_cell(nb: NotebookNode, cell_id: str) -> None:
    nb.cells.pop(_index(nb, cell_id))


def move_cell(nb: NotebookNode, cell_id: str, direction: Direction) -> None:
    """Move one place up or down; moving past either end does nothing."""
    if direction not in DIRECTIONS:
        raise WorkspaceError(ErrorCode.BAD_PAYLOAD, "Cells move up or down.")
    i = _index(nb, cell_id)
    j = i - 1 if direction == "up" else i + 1
    if 0 <= j < len(nb.cells):
        nb.cells[i], nb.cells[j] = nb.cells[j], nb.cells[i]


def reorder_cell(nb: NotebookNode, cell_id: str, before_id: str | None = None) -> None:
    """Move a cell to just before `before_id`, or to the end when it is None."""
    i = _index(nb, cell_id)
    if before_id == cell_id:
        return
    j = len(nb.cells) if before_id is None else _index(nb, before_id)
    cell = nb.cells.pop(i)
    if j > i:
        j -= 1
    nb.cells.insert(j, cell)


def duplicate_cell(nb: NotebookNode, cell_id: str) -> NotebookNode:
    """Copy a cell's type and source right below it; outputs start empty."""
    cell = find_cell(nb, cell_id)
    if cell.cell_type == "code":
        new = nbformat.v4.new_code_cell(cell.source)
    else:
        new = nbformat.v4.new_markdown_cell(cell.source)
    nb.cells.insert(_index(nb, cell_id) + 1, new)
    return new


def clear_cell_outputs(nb: NotebookNode, cell_id: str) -> None:
    """Clear one code cell's outputs and run number; keep its source."""
    cell = find_cell(nb, cell_id)
    if cell.cell_type != "code":
        raise WorkspaceError(ErrorCode.NOT_CODE, "Notes don't have outputs.")
    cell.outputs = []
    cell.execution_count = None
    cell.metadata.pop("researchchat", None)


def clear_outputs(nb: NotebookNode) -> None:
    """Clear outputs and run numbers of all code cells; keep sources."""
    for cell in nb.cells:
        if cell.cell_type == "code":
            cell.outputs = []
            cell.execution_count = None
            cell.metadata.pop("researchchat", None)
