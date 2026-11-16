"""Created-dataset rows in project_datasets: storage and constraints (PCD-1 plan §3.3, §7).

Plan: docs/plans/PCD-1-created-datasets-plan.md §7
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from researchchat.db.engine import database_for
from researchchat.workspace import store
from researchchat.workspace.datasets import created_store as cds
from researchchat.workspace.datasets.created import CreatedDatasets
from researchchat.workspace.datasets.created_store import CreatedDataset, FileSnapshot

IRIS = FileSnapshot(path="Iris.csv", size_bytes=4551, mtime_ns=1_763_000_000_000_000_000, inode=812_345)


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "workspaces"
    store.create_project("P", root, project_id="p")
    return root


def created_iris(snapshot: FileSnapshot = IRIS, dataset_id: str = "file-iris-csv") -> CreatedDataset:
    return CreatedDataset(id=dataset_id, snapshot=snapshot, first_seen_at="2026-11-16T09:12:03Z", changed_at="2026-11-16T09:12:03Z")


def insert_raw_row(root, columns: str, values: str) -> None:
    """A row written straight with SQL, as a bug or a hand edit could (constraint tests)."""
    with database_for(root).begin() as connection:
        connection.execute(text(f"INSERT INTO project_datasets (project_pk, slug, position, status, {columns}) VALUES (1, 'file-x', 0, 'ready', {values})"))


def insert_pool_entry(root) -> None:
    with database_for(root).begin() as connection:
        connection.execute(text(
            "INSERT INTO pool_entries (slug, source, source_id, name, created_at) VALUES ('hf-x@1', 'huggingface', 'o/x', 'X', 't')"
        ))


# ---- PCD-1 Group 3 — Saving again updates, never duplicates (AC4) · integration
# Baseline: Given `Iris.csv` stored as a created row · When the same path is stored again


def test_same_path_twice_is_rejected_by_unique_constraint(root):
    # G3❌1 · negative
    # Changed: insert the same (`project_pk`, `path`) directly
    # Then: `IntegrityError`
    # Demonstrates: the DB itself guards against duplicates
    cds.insert_created_dataset("p", created_iris(), root)

    with pytest.raises(IntegrityError):
        cds.insert_created_dataset("p", created_iris(dataset_id="file-iris-csv-2"), root)

    assert [d.id for d in cds.load_created_datasets("p", root)] == ["file-iris-csv"]


# ---- PCD-1 Group 10 — Storage: both kinds in one table (D2, §3.3) · integration (real SQLite)
# Baseline: Given a migrated database with project `p` · When created rows are stored and read


def test_created_row_round_trips(root):
    # G10✅1 · baseline
    # Changed: —
    # Then: load returns path, size, mtime, inode, id as saved
    # Demonstrates: created rows are stored faithfully
    cds.insert_created_dataset("p", created_iris(), root)

    assert cds.load_created_datasets("p", root) == [created_iris()]


def test_created_row_with_pool_entry_is_rejected(root):
    # G10❌2 · negative
    # Changed: created row with `pool_entry_pk` set
    # Then: `IntegrityError` (`origin_shape`)
    # Demonstrates: a row is one kind only
    insert_pool_entry(root)

    with pytest.raises(IntegrityError, match="origin_shape"):
        insert_raw_row(root, "origin, pool_entry_pk, path, size_bytes, mtime_ns", "'created', 1, 'x.csv', 1, 1")


def test_downloaded_row_without_pool_entry_is_rejected(root):
    # G10❌3 · negative
    # Changed: downloaded row, NULL pool entry
    # Then: `IntegrityError`
    # Demonstrates: downloads keep their pool link
    with pytest.raises(IntegrityError, match="origin_shape"):
        insert_raw_row(root, "origin", "'downloaded'")


def test_created_row_without_path_is_rejected(root):
    # G10❌4 · negative
    # Changed: created row, NULL path
    # Then: `IntegrityError`
    # Demonstrates: a created card always has a file path
    with pytest.raises(IntegrityError, match="origin_shape"):
        insert_raw_row(root, "origin, size_bytes, mtime_ns", "'created', 1, 1")


def test_unknown_origin_is_rejected(root):
    # G10❌6 · negative
    # Changed: `origin = 'uploaded'`
    # Then: `IntegrityError` (`origin_known`)
    # Demonstrates: only the two known kinds exist
    with pytest.raises(IntegrityError, match="origin_known"):
        insert_raw_row(root, "origin, path, size_bytes, mtime_ns", "'uploaded', 'x.csv', 1, 1")


# ---- PCD-1 Group S1 — Delete never follows links (SEC4) · integration
# Baseline: Given a created row whose path was hand-edited in the database


def test_tampered_row_path_is_skipped(root, caplog):
    # S1❌5 · negative
    # Changed: row path `../../q/files/x.csv`
    # Then: row ignored + logged; delete → `NOT_FOUND`
    # Demonstrates: DB rows aren't trusted blindly
    insert_raw_row(root, "origin, path, size_bytes, mtime_ns", "'created', '../../q/files/x.csv', 1, 1")

    assert cds.load_created_datasets("p", root) == []
    assert "Ignored a created dataset row" in caplog.text
    assert CreatedDatasets(root).owns("p", "file-x") is False
