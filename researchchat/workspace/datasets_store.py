"""Datasets of a project: database rows, and their links on disk.

workspaces/
    researchchat.db                    project_datasets + project_dataset_files (one row per dataset)
    <project_id>/files/datasets/<id>/  links into the shared pool (seen by the kernel at /work/datasets/<id>/)

The database sits at the workspaces root, outside every kernel mount, so kernel
code can't edit it. This module only reads and writes storage: no locks, no
network. The rules (who may delete, when to download) live in dataset_service.py.

Plans: docs/plans/done/NB-3-dataset-download-plan.md, docs/plans/sqlite-alembic-storage-plan.md
"""

import logging
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

from sqlalchemy import Connection, Row, Select, delete, insert, select

from researchchat.config import WORKSPACES_DIR
from researchchat.db.engine import database_for
from researchchat.db.schema import (
    pool_entries,
    project_dataset_files,
    project_datasets,
    projects,
)
from researchchat.workspace import ErrorCode, WorkspaceError, store

log = logging.getLogger(__name__)

DATASETS_DIR = "datasets"  # under the project's files/
DATASET_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
DATASET_ID_MAX = 80
NAME_MAX = 200
PATH_MAX = 1024
KERNEL_ROOT = "/work/datasets"  # how the kernel sees files/datasets/
DRIVE_RE = re.compile(r"^[A-Za-z]:")

Source = Literal["huggingface", "zenodo"]
StoredStatus = Literal["queued", "downloading", "ready", "failed"]
ORIGIN_DOWNLOADED = "downloaded"  # project_datasets.origin of a catalog download (PCD-1)
DatasetStatus = Literal["queued", "downloading", "ready", "failed", "missing"]  # missing is computed on read


def slug_of(text: str) -> str:
    """Lowercase ASCII words joined by '-': the readable part of a dataset id."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def base_id(source: Source, source_id: str) -> str:
    """hf-<owner>--<name> / zenodo-<id>: the readable slug of a catalog dataset."""
    prefix = "hf" if source == "huggingface" else source
    body = "--".join(p for p in (slug_of(part) for part in source_id.split("/")) if p) or "dataset"
    return re.sub(r"-{3,}", "--", f"{prefix}-{body}")[:DATASET_ID_MAX].strip("-")


def make_id(source: Source, source_id: str, taken_ids: set[str]) -> str:
    """base_id, with -2, -3… when another dataset of the project already has it."""
    base = base_id(source, source_id)
    candidate, n = base, 2
    while candidate in taken_ids:
        suffix = f"-{n}"
        candidate = base[: DATASET_ID_MAX - len(suffix)].rstrip("-") + suffix
        n += 1
    return candidate


def safe_relpath(name) -> str:
    """A catalog file name as a safe relative POSIX path; WorkspaceError if unsafe."""
    bad = WorkspaceError(ErrorCode.BAD_PAYLOAD, f"Unsafe file name in the dataset: {str(name)[:80]!r}")
    if not isinstance(name, str) or not name.strip() or len(name) > PATH_MAX:
        raise bad
    if "\\" in name or "\x00" in name or name.startswith("/") or DRIVE_RE.match(name):
        raise bad
    parts = [p for p in PurePosixPath(name).parts if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        raise bad
    return "/".join(parts)


def _check_id(dataset_id) -> None:
    if not isinstance(dataset_id, str) or not DATASET_ID_RE.match(dataset_id):
        raise WorkspaceError(ErrorCode.NOT_FOUND, "Unknown dataset.")


def _linked() -> WorkspaceError:
    return WorkspaceError(ErrorCode.DOWNLOAD_FAILED, "the dataset folder is a link, so it wasn't used")


def datasets_root(project_id: str, root: Path = WORKSPACES_DIR) -> Path:
    """files/datasets/. Kernel code can replace it with a symlink (files/ is /work,
    read-write), so it's never resolved through: a link here is refused (SEC2, SEC8)."""
    base = (store.project_dir(project_id, root) / store.FILES_DIR).resolve() / DATASETS_DIR
    if base.resolve() != base:
        raise _linked()
    return base


def dataset_dir(project_id: str, dataset_id: str, root: Path = WORKSPACES_DIR) -> Path:
    """files/datasets/<id>/; refused when it or files/datasets is a link."""
    _check_id(dataset_id)
    folder = datasets_root(project_id, root) / dataset_id
    if folder.resolve() != folder:
        raise _linked()
    return folder


def path_inside(folder: Path, relpath: str) -> Path:
    """folder/relpath; must stay under the folder after resolve()."""
    base = folder.resolve()
    path = (base / safe_relpath(relpath)).resolve()
    if path == base or not path.is_relative_to(base):
        raise WorkspaceError(ErrorCode.BAD_PAYLOAD, "Unsafe file name in the dataset.")
    return path


def file_path(project_id: str, dataset_id: str, relpath: str, root: Path = WORKSPACES_DIR) -> Path:
    """One file of files/datasets/<id>/, resolved; must stay under it."""
    return path_inside(dataset_dir(project_id, dataset_id, root), relpath)


def kernel_path(dataset_id: str, relpath: str = "") -> str:
    """/work/datasets/<id>/<relpath>: the path the model and the kernel use."""
    return f"{KERNEL_ROOT}/{dataset_id}" + (f"/{relpath}" if relpath else "")


# ---- disk state ---------------------------------------------------------------


def remove_tree(path: Path) -> None:
    """Remove a folder (or a symlink in its place) without following links."""
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def remove_dataset_dir(project_id: str, dataset_id: str, root: Path = WORKSPACES_DIR) -> None:
    """Delete files/datasets/<id>/ only; record file paths are ignored.

    Links are never followed: a linked <id> is unlinked, and when files/datasets
    itself is a link nothing is touched (none of it is ours).
    """
    _check_id(dataset_id)
    try:
        base = datasets_root(project_id, root)
    except WorkspaceError:
        return
    remove_tree(base / dataset_id)


# ---- project datasets: rows pointing at shared pool entries (NB-4 plan §3.3) --------

STORED_STATUSES = ("queued", "downloading", "ready", "failed")


@dataclass
class ProjectDataset:
    id: str  # generated slug, folder name under files/datasets/
    pool_entry: str  # which pooled version this project uses; changes only with update: true
    selection: list[str] | None  # every `files` pattern asked for so far; None = all files
    status: StoredStatus
    files: list[str] = field(default_factory=list)  # paths only; sizes and checksums live in the pool entry
    requested_at: str = ""  # ISO 8601 UTC; queue order
    linked_at: str | None = None  # when this project got the files (may be long after the pool did)
    error: str | None = None  # one-line reason when failed


def load_project_datasets(project_id: str, root: Path = WORKSPACES_DIR) -> list[ProjectDataset]:
    """The project's datasets from the database, in list order; a tampered row is skipped and logged (SEC3)."""
    store.project_dir(project_id, root)  # NOT_FOUND for an id that isn't a safe slug
    with database_for(root).connect() as connection:
        rows = connection.execute(_project_datasets_query(project_id)).all()
        files_by_dataset = _files_by_dataset(connection, [row.pk for row in rows])
    datasets = (_project_dataset_from_row(row, files_by_dataset.get(row.pk, [])) for row in rows)
    return [dataset for dataset in datasets if dataset is not None]


def save_project_datasets(project_id: str, datasets: list[ProjectDataset], root: Path = WORKSPACES_DIR) -> None:
    """Replace the project's datasets in one transaction. Their pool entries must be saved first (FK)."""
    store.project_dir(project_id, root)
    with database_for(root).begin() as connection:
        project_pk = _project_pk(connection, project_id)
        entry_pks = _pool_entry_pks(connection, {dataset.pool_entry for dataset in datasets})
        # Created rows share this table (PCD-1); a replace-all of every row would wipe them
        connection.execute(delete(project_datasets).where(
            project_datasets.c.project_pk == project_pk, project_datasets.c.origin == ORIGIN_DOWNLOADED
        ))
        for position, dataset in enumerate(datasets):
            _insert_project_dataset(connection, project_pk, entry_pks[dataset.pool_entry], position, dataset)


class UnknownPoolEntry(ValueError):
    """A project dataset names a pool entry the database doesn't have (save the index first)."""


def _project_datasets_query(project_id: str) -> Select:
    return (
        select(
            project_datasets.c.pk, project_datasets.c.slug, pool_entries.c.slug.label("pool_entry"),
            project_datasets.c.selection, project_datasets.c.status, project_datasets.c.requested_at,
            project_datasets.c.linked_at, project_datasets.c.error,
        )
        .join(projects, projects.c.pk == project_datasets.c.project_pk)
        .join(pool_entries, pool_entries.c.pk == project_datasets.c.pool_entry_pk)
        .where(projects.c.slug == project_id, project_datasets.c.origin == ORIGIN_DOWNLOADED)
        .order_by(project_datasets.c.position)
    )


def _files_by_dataset(connection: Connection, dataset_pks: list[int]) -> dict[int, list[str]]:
    rows = connection.execute(
        select(project_dataset_files.c.dataset_pk, project_dataset_files.c.path)
        .where(project_dataset_files.c.dataset_pk.in_(dataset_pks))
        .order_by(project_dataset_files.c.dataset_pk, project_dataset_files.c.position)
    )
    files: dict[int, list[str]] = {}
    for row in rows:
        files.setdefault(row.dataset_pk, []).append(row.path)
    return files


def _project_dataset_from_row(row: Row, files: list[str]) -> ProjectDataset | None:
    """A ProjectDataset, or None (logged) when the row was edited into something unsafe."""
    is_list_of_patterns = isinstance(row.selection, list) and all(isinstance(p, str) for p in row.selection)
    is_valid = DATASET_ID_RE.match(row.slug) and row.status in STORED_STATUSES
    if not is_valid or not (row.selection is None or is_list_of_patterns):
        log.warning("Ignored a dataset row that isn't valid: %r", row.slug[:80])
        return None
    return ProjectDataset(
        id=row.slug, pool_entry=row.pool_entry, selection=row.selection, status=row.status, files=files,
        requested_at=row.requested_at, linked_at=row.linked_at, error=row.error,
    )


def _project_pk(connection: Connection, project_id: str) -> int:
    project_pk = connection.scalar(select(projects.c.pk).where(projects.c.slug == project_id))
    if project_pk is None:
        raise WorkspaceError(ErrorCode.NOT_FOUND, "Unknown project.")
    return project_pk


def _pool_entry_pks(connection: Connection, entry_slugs: set[str]) -> dict[str, int]:
    rows = connection.execute(select(pool_entries.c.slug, pool_entries.c.pk).where(pool_entries.c.slug.in_(entry_slugs)))
    entry_pks = {row.slug: row.pk for row in rows}
    unknown = sorted(entry_slugs - entry_pks.keys())
    if unknown:
        raise UnknownPoolEntry(f"pool entries not saved yet: {unknown}")
    return entry_pks


def _insert_project_dataset(
    connection: Connection, project_pk: int, entry_pk: int, position: int, dataset: ProjectDataset
) -> None:
    dataset_pk = connection.execute(insert(project_datasets).values(
        project_pk=project_pk, slug=dataset.id, pool_entry_pk=entry_pk, position=position,
        selection=dataset.selection, status=dataset.status, requested_at=dataset.requested_at,
        linked_at=dataset.linked_at, error=dataset.error,
    )).inserted_primary_key[0]
    if dataset.files:
        connection.execute(
            insert(project_dataset_files),
            [{"dataset_pk": dataset_pk, "position": i, "path": path} for i, path in enumerate(dataset.files)],
        )


def find_project_dataset(datasets: list[ProjectDataset], dataset_id: str) -> ProjectDataset | None:
    """The dataset with this id among this project's datasets."""
    return next((d for d in datasets if d.id == dataset_id), None)


def link_path(project_id: str, dataset_id: str, relpath: str, root: Path = WORKSPACES_DIR) -> Path:
    """files/datasets/<id>/<relpath>, not resolved (it's a link). Refused when a folder on the way is a link (SEC23)."""
    folder = dataset_dir(project_id, dataset_id, root)
    path = folder / safe_relpath(relpath)
    for parent in path.relative_to(folder).parents:
        if (folder / parent).is_symlink():
            raise _linked()
    return path
