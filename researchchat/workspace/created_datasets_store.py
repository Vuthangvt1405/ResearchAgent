"""Created datasets of a project: `project_datasets` rows with origin = 'created'.

A created dataset is a data file the project's own notebook code wrote into
files/ (seen by the kernel as /work/<path>). It has no pool entry and no
project_dataset_files rows; its path, size, mtime and inode live on the row
itself (PCD-1 plan §3.3). This module only reads and writes those rows; the
rules (what counts, renames, safe delete) live in created_datasets.py.

Plan: docs/plans/PCD-1-created-datasets-plan.md
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Connection, Row, delete, func, insert, select, update

from researchchat.config import WORKSPACES_DIR
from researchchat.db.engine import database_for
from researchchat.db.schema import project_datasets, projects
from researchchat.workspace import ErrorCode, WorkspaceError, store
from researchchat.workspace import datasets_store as ds

log = logging.getLogger(__name__)

ORIGIN_CREATED = "created"
CREATED_ID_PREFIX = "file-"  # can't clash with catalog ids (hf-, zenodo-), so ds_delete routes by lookup (A3)
KERNEL_FILES_ROOT = "/work"  # how the kernel sees the project's files/
STORED_STATUS = "ready"  # created rows are always stored ready; missing is computed on read


@dataclass(frozen=True)
class FileSnapshot:
    """What one scan saw of a data file: enough to spot a re-save (AC4) or a rename (AC12)."""

    path: str  # POSIX, relative to files/
    size_bytes: int
    mtime_ns: int  # changes on every save; part of the rename match
    inode: int  # kept by a rename; with size and mtime it finds the card of a renamed file (SEC10)


@dataclass
class CreatedDataset:
    """One created card, as stored."""

    id: str  # stored slug (file-iris-csv); kept on rename (A3, D7)
    snapshot: FileSnapshot  # path, size, mtime, inode at the last scan that changed it
    first_seen_at: str  # ISO 8601 UTC, project_datasets.requested_at; sort order (A8)
    changed_at: str  # ISO 8601 UTC, project_datasets.linked_at; "added 2 h ago"


def make_created_id(path: str, taken_ids: set[str]) -> str:
    """file-<slug of path>, with -2, -3… when the project already has that id."""
    body = ds.slug_of(path) or "data"
    base = (CREATED_ID_PREFIX + body)[: ds.DATASET_ID_MAX].strip("-")
    candidate, suffix_number = base, 2
    while candidate in taken_ids:
        suffix = f"-{suffix_number}"
        candidate = base[: ds.DATASET_ID_MAX - len(suffix)].rstrip("-") + suffix
        suffix_number += 1
    return candidate


def kernel_file_path(path: str) -> str:
    """/work/<path>: the path the model, the card and the load code use (AC1, AC6)."""
    return f"{KERNEL_FILES_ROOT}/{path}"


def load_created_datasets(project_id: str, root: Path = WORKSPACES_DIR) -> list[CreatedDataset]:
    """The project's created rows in list order; a tampered row (unsafe path, bad id) is skipped and logged."""
    store.project_dir(project_id, root)  # NOT_FOUND for an id that isn't a safe slug
    query = (
        select(
            project_datasets.c.slug, project_datasets.c.path, project_datasets.c.size_bytes,
            project_datasets.c.mtime_ns, project_datasets.c.inode, project_datasets.c.requested_at,
            project_datasets.c.linked_at,
        )
        .join(projects, projects.c.pk == project_datasets.c.project_pk)
        .where(projects.c.slug == project_id, project_datasets.c.origin == ORIGIN_CREATED)
        .order_by(project_datasets.c.position)
    )
    with database_for(root).connect() as connection:
        rows = connection.execute(query).all()
    datasets = (_created_dataset_from_row(row) for row in rows)
    return [dataset for dataset in datasets if dataset is not None]


def insert_created_dataset(project_id: str, dataset: CreatedDataset, root: Path = WORKSPACES_DIR) -> None:
    """Add one created row (origin = 'created', no pool entry, status 'ready'), after every other row."""
    with database_for(root).begin() as connection:
        project_pk = _project_pk(connection, project_id)
        connection.execute(insert(project_datasets).values(
            project_pk=project_pk, slug=dataset.id, origin=ORIGIN_CREATED, position=_next_position(connection, project_pk),
            status=STORED_STATUS, requested_at=dataset.first_seen_at, linked_at=dataset.changed_at,
            **_snapshot_columns(dataset.snapshot),
        ))


def update_created_dataset(project_id: str, dataset: CreatedDataset, root: Path = WORKSPACES_DIR) -> None:
    """Store a new snapshot for an existing id: a re-save (AC4) or a rename/move (AC12)."""
    with database_for(root).begin() as connection:
        connection.execute(
            update(project_datasets)
            .where(*_created_row_of(connection, project_id, dataset.id))
            .values(linked_at=dataset.changed_at, **_snapshot_columns(dataset.snapshot))
        )


def delete_created_dataset(project_id: str, dataset_id: str, root: Path = WORKSPACES_DIR) -> None:
    """Remove one created row; the file on disk is handled by created_datasets.py."""
    with database_for(root).begin() as connection:
        connection.execute(delete(project_datasets).where(*_created_row_of(connection, project_id, dataset_id)))


def _snapshot_columns(snapshot: FileSnapshot) -> dict[str, object]:
    return {"path": snapshot.path, "size_bytes": snapshot.size_bytes, "mtime_ns": snapshot.mtime_ns, "inode": snapshot.inode}


def _created_row_of(connection: Connection, project_id: str, dataset_id: str) -> tuple:
    """WHERE clauses for one created row of one project; a downloaded row with that id is never matched."""
    return (
        project_datasets.c.project_pk == _project_pk(connection, project_id),
        project_datasets.c.slug == dataset_id,
        project_datasets.c.origin == ORIGIN_CREATED,
    )


def _project_pk(connection: Connection, project_id: str) -> int:
    project_pk = connection.scalar(select(projects.c.pk).where(projects.c.slug == project_id))
    if project_pk is None:
        raise WorkspaceError(ErrorCode.NOT_FOUND, "Unknown project.")
    return project_pk


def _next_position(connection: Connection, project_pk: int) -> int:
    highest = connection.scalar(
        select(func.max(project_datasets.c.position)).where(project_datasets.c.project_pk == project_pk)
    )
    return 0 if highest is None else highest + 1


def _created_dataset_from_row(row: Row) -> CreatedDataset | None:
    """A CreatedDataset, or None (logged) when the row was edited into something unsafe (SEC4)."""
    has_valid_id = bool(ds.DATASET_ID_RE.match(row.slug)) and row.slug.startswith(CREATED_ID_PREFIX)
    if not has_valid_id or not _is_safe_path(row.path):
        log.warning("Ignored a created dataset row that isn't valid: %r", str(row.slug)[:80])
        return None
    snapshot = FileSnapshot(path=row.path, size_bytes=row.size_bytes, mtime_ns=row.mtime_ns, inode=row.inode or 0)
    return CreatedDataset(id=row.slug, snapshot=snapshot, first_seen_at=row.requested_at, changed_at=row.linked_at or "")


def _is_safe_path(path: str) -> bool:
    """Same rule as catalog file names: relative, no '..', no drive or backslash (datasets_store.safe_relpath)."""
    try:
        return ds.safe_relpath(path) == path
    except WorkspaceError:
        return False
