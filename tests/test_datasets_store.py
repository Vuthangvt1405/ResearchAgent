"""Tests for project datasets in the database, dataset ids and safe paths (NB-3 plan §7: S❌2, make_id; SQLite plan G3)."""

from dataclasses import fields

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from researchchat.config import DATABASE_FILE
from researchchat.db.engine import database_for
from researchchat.workspace import WorkspaceError, store
from researchchat.workspace.datasets import store as ds
from researchchat.workspace.datasets.pool import DatasetPool, PoolEntry, PoolFile


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "workspaces"
    store.create_project("P1", root, project_id="p1")
    return root


# ---- Group 6 — Dataset ids · unit


def test_make_id_suffixes_clashes():
    # G6 (added in implementation; NB-4: the same dataset is found through its pool entry, not by id)
    # Changed: ids that collide · Then: readable slug; -2 for a different dataset with the same slug
    # Demonstrates: two datasets never share a folder
    assert ds.make_id("huggingface", "David-Egea/Creditcard-fraud-detection", set()) == "hf-david-egea--creditcard-fraud-detection"
    assert ds.make_id("zenodo", "7395559", set()) == "zenodo-7395559"
    assert ds.make_id("huggingface", "org/name", set()) == "hf-org--name"
    assert ds.make_id("huggingface", "Org/Name", {"hf-org--name"}) == "hf-org--name-2"
    long_id = ds.make_id("huggingface", "o/" + "x" * 200, set())
    assert len(long_id) <= 80 and ds.DATASET_ID_RE.match(long_id)


# ---- Group S — Security (§5 #2, #8) · unit
# Baseline: negatives only; Given a project on tmp_path


def test_dataset_paths_stay_inside_dataset_folder(root):
    # S❌2 · Changed: crafted id / file path
    # Then: refused; nothing written outside
    # Demonstrates: traversal (#2)
    for bad_id in ("../p1", "a/b", "", "UPPER", "x" * 81, None):
        with pytest.raises(WorkspaceError):
            ds.dataset_dir("p1", bad_id, root)
    for bad_path in ("../x", "a/../../x", "/etc/passwd", "a\\b", "C:/x", "a\x00b", "", "  ", ".", 5):
        with pytest.raises(WorkspaceError):
            ds.file_path("p1", "hf-org--name", bad_path, root)
    assert ds.safe_relpath("data/./train.csv") == "data/train.csv"
    inside = ds.file_path("p1", "hf-org--name", "data/train.csv", root)
    assert inside.is_relative_to(ds.dataset_dir("p1", "hf-org--name", root))
    assert sorted(p.name for p in root.iterdir() if not p.name.startswith(DATABASE_FILE)) == ["p1"]


# ---- SQLite plan G3 — Project datasets in the database (AC3, SEC3, SEC4, SEC5) · integration
# Baseline: Given project `p1` and pool entry `hf-org--name@r1` · When `save_project_datasets("p1", [dataset])` then `load_project_datasets("p1")`
# Plan: docs/plans/sqlite-alembic-storage-plan.md §7

ENTRY = "hf-org--name@r1"


@pytest.fixture
def pool(root):
    """The baseline pool entry, saved, so project datasets can point to it."""
    pool = DatasetPool(root)
    pool.add_entry(PoolEntry(ENTRY, "huggingface", "org/name", "r1", "org/name", None, "mit",
                             [PoolFile("a.csv", 3, None, True)]))
    pool.save_index()
    return pool


def dataset(id="hf-org--name", files=("a.csv",), selection=None, status="ready"):
    return ds.ProjectDataset(
        id=id, pool_entry=ENTRY, selection=selection, status=status, files=list(files),
        requested_at="2026-11-15T00:00:00+00:00", linked_at="2026-11-15T00:00:01+00:00", error=None,
    )


def test_project_datasets_round_trip(root, pool):
    # G3✅1 · baseline
    # Changed: —
    # Then: an equal ProjectDataset (every field), same list order
    # Demonstrates: nothing is lost between dataclass and rows
    saved = [dataset(), dataset("zenodo-1", status="failed")]
    saved[1].error = "checksum mismatch"

    ds.save_project_datasets("p1", saved, root)

    assert ds.load_project_datasets("p1", root) == saved


def test_selection_none_and_empty_list_stay_distinct(root, pool):
    # G3✅2 · edge
    # Changed: selection=None and selection=[] on two datasets
    # Then: read back as None and []
    # Demonstrates: "all files" never turns into "no files"
    ds.save_project_datasets("p1", [dataset("all-files", selection=None), dataset("no-files", selection=[])], root)

    assert [d.selection for d in ds.load_project_datasets("p1", root)] == [None, []]


def test_file_order_is_kept(root, pool):
    # G3✅3 · edge
    # Changed: files=["b.csv", "a.csv", "dir/c.csv"]
    # Then: same order
    # Demonstrates: the panel lists files as before
    ds.save_project_datasets("p1", [dataset(files=("b.csv", "a.csv", "dir/c.csv"))], root)

    assert ds.load_project_datasets("p1", root)[0].files == ["b.csv", "a.csv", "dir/c.csv"]


def test_saving_a_shorter_list_removes_dropped_datasets(root, pool):
    # G3✅4 · edge
    # Changed: save 2, then save 1
    # Then: 1 row and its files only
    # Demonstrates: delete still works through "save the list"
    ds.save_project_datasets("p1", [dataset("first"), dataset("second")], root)
    ds.save_project_datasets("p1", [dataset("second")], root)

    assert [d.id for d in ds.load_project_datasets("p1", root)] == ["second"]
    with database_for(root).connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM project_dataset_files")).scalar() == 1


def test_same_dataset_slug_in_two_projects_is_allowed(root, pool):
    # G3✅5 · edge
    # Changed: p1 and p2 both save zenodo-10117394 → the same pool entry
    # Then: two rows, same pool_entry_pk; each project loads its own
    # Demonstrates: the shared pool works with per-project unique slugs (D1, D2)
    store.create_project("P2", root, project_id="p2")
    ds.save_project_datasets("p1", [dataset("zenodo-10117394", files=("a.csv",))], root)
    ds.save_project_datasets("p2", [dataset("zenodo-10117394", files=())], root)

    with database_for(root).connect() as connection:
        entry_pks = connection.execute(text("SELECT DISTINCT pool_entry_pk FROM project_datasets")).scalars().all()
    assert len(entry_pks) == 1
    assert ds.load_project_datasets("p1", root)[0].files == ["a.csv"]
    assert ds.load_project_datasets("p2", root)[0].files == []
    assert pool.projects_using(ENTRY) == ["p1", "p2"]


def test_integer_keys_never_reach_the_dataclasses(root, pool):
    # G3✅6 · edge
    # Changed: —
    # Then: the loaded ProjectDataset has exactly today's fields; pool_entry is the slug string
    # Demonstrates: the integer keys stay inside the storage layer
    ds.save_project_datasets("p1", [dataset()], root)

    [loaded] = ds.load_project_datasets("p1", root)

    assert [f.name for f in fields(ds.ProjectDataset)] == [
        "id", "pool_entry", "selection", "status", "files", "requested_at", "linked_at", "error",
    ]
    assert loaded.pool_entry == ENTRY


def test_failed_save_keeps_previous_datasets(root, pool, monkeypatch):
    # G3❌1 · negative
    # Changed: the second insert raises mid-transaction
    # Then: previous rows unchanged
    # Demonstrates: a crash never leaves half a list
    ds.save_project_datasets("p1", [dataset("kept")], root)
    real_insert = ds._insert_project_dataset
    inserted = []

    def fail_on_second(*args):
        inserted.append(args)
        if len(inserted) == 2:
            raise OSError("disk full")
        real_insert(*args)

    monkeypatch.setattr(ds, "_insert_project_dataset", fail_on_second)

    with pytest.raises(OSError, match="disk full"):
        ds.save_project_datasets("p1", [dataset("new-1"), dataset("new-2")], root)

    assert [d.id for d in ds.load_project_datasets("p1", root)] == ["kept"]


def test_tampered_dataset_row_is_skipped(root, pool, caplog):
    # G3❌2 · negative · replaces test_corrupt_manifest_is_set_aside
    # Changed: rows with slug ../x and status "hacked" inserted by hand
    # Then: skipped with a warning; good rows still returned
    # Demonstrates: tampered data never becomes a path or a status
    ds.save_project_datasets("p1", [dataset("good")], root)
    with database_for(root).begin() as connection:
        connection.execute(text("PRAGMA ignore_check_constraints = ON"))  # a hand edit, past the CHECKs
        for position, (slug, status) in enumerate([("../x", "ready"), ("bad-status", "hacked")], start=1):
            connection.execute(text(
                "INSERT INTO project_datasets (project_pk, slug, pool_entry_pk, position, status) "
                "SELECT p.pk, :slug, e.pk, :position, :status FROM projects p, pool_entries e WHERE p.slug = 'p1'"
            ), {"slug": slug, "position": position, "status": status})

    assert [d.id for d in ds.load_project_datasets("p1", root)] == ["good"]
    assert caplog.text.count("Ignored a dataset row") == 2


def test_other_projects_datasets_are_not_returned(root, pool):
    # G3❌3 · negative
    # Changed: p2 has a dataset too
    # Then: load("p1") returns only p1's
    # Demonstrates: projects only read their own datasets
    store.create_project("P2", root, project_id="p2")
    ds.save_project_datasets("p1", [dataset("mine")], root)
    ds.save_project_datasets("p2", [dataset("theirs")], root)

    assert [d.id for d in ds.load_project_datasets("p1", root)] == ["mine"]


def test_dataset_pointing_to_unknown_pool_entry_is_refused(root, pool):
    # G3❌4 · negative
    # Changed: pool_entry="nope" (no pool_entries row has that slug)
    # Then: refused before any write; previous rows unchanged
    # Demonstrates: the slug → pk lookup can't create a dangling reference
    ds.save_project_datasets("p1", [dataset("kept")], root)
    dangling = dataset("dangling")
    dangling.pool_entry = "nope"

    with pytest.raises(ds.UnknownPoolEntry):
        ds.save_project_datasets("p1", [dangling], root)

    assert [d.id for d in ds.load_project_datasets("p1", root)] == ["kept"]


def test_duplicate_dataset_slug_in_one_project_is_refused(root, pool):
    # G3❌5 · negative
    # Changed: two datasets with slug hf-org--name in one save
    # Then: IntegrityError (UNIQUE); previous rows unchanged
    # Demonstrates: two datasets never share a folder
    ds.save_project_datasets("p1", [dataset("kept")], root)

    with pytest.raises(IntegrityError):
        ds.save_project_datasets("p1", [dataset("hf-org--name"), dataset("hf-org--name")], root)

    assert [d.id for d in ds.load_project_datasets("p1", root)] == ["kept"]


def test_delete_ignores_tampered_rows(root, pool):
    # G3❌6 · negative · rewrite of test_delete_ignores_tampered_manifests
    # Changed: a dataset row whose file paths point outside files/datasets/<id>/
    # Then: delete removes only files/datasets/<id>/; nothing else
    # Demonstrates: delete never follows data it reads back
    pool_file = pool.pool_file_path(ENTRY, "a.csv")
    pool_file.parent.mkdir(parents=True)
    pool_file.write_text("abc")
    folder = ds.dataset_dir("p1", "hf-org--name", root)
    folder.mkdir(parents=True)
    (folder / "a.csv").symlink_to(pool.link_target(ENTRY, "a.csv"))
    other = ds.dataset_dir("p1", "zenodo-1", root)
    other.mkdir()
    ds.save_project_datasets("p1", [dataset(files=("../../notebook.ipynb",))], root)
    with database_for(root).begin() as connection:  # the pool entry's slug edited by hand too
        connection.execute(text("UPDATE pool_entries SET slug = '../x'"))

    [tampered] = ds.load_project_datasets("p1", root)
    pool = DatasetPool(root)  # a fresh read of the index, as after a restart
    pool.unlink_dataset("p1", tampered.id)
    assert pool.remove_unused_entry(tampered.pool_entry) == 0
    with pytest.raises(WorkspaceError):
        pool.entry_dir(tampered.pool_entry)

    assert (store.project_dir("p1", root) / "notebook.ipynb").is_file()
    assert not folder.exists()
    assert other.is_dir()
    assert pool_file.read_text() == "abc"


# ---- PCD-1 Group 10 — Storage: both kinds in one table (D2, §3.3) · integration (real SQLite)
# Baseline: Given project `p1` with a downloaded dataset `hf-x` and a created row `file-iris-csv` · When downloaded datasets are saved or loaded


@pytest.fixture
def project_with_both_kinds(root):
    from researchchat.workspace.datasets import created_store as cds

    pool = DatasetPool(root)
    pool.add_entry(PoolEntry("hf-x@1", "huggingface", "o/x", None, "X", None, None, [PoolFile("a.csv", 1, None, True)]))
    pool.save_index()
    ds.save_project_datasets("p1", [ds.ProjectDataset("hf-x", "hf-x@1", None, "ready", ["a.csv"])], root)
    snapshot = cds.FileSnapshot(path="Iris.csv", size_bytes=4551, mtime_ns=1, inode=1)
    cds.insert_created_dataset("p1", cds.CreatedDataset("file-iris-csv", snapshot, "t", "t"), root)
    return root


def test_saving_downloaded_datasets_keeps_created_rows(project_with_both_kinds):
    # G10❌1 · negative
    # Changed: `save_project_datasets(p, [...])`
    # Then: `file-iris-csv` row still there
    # Demonstrates: a download can't wipe created cards
    from researchchat.workspace.datasets import created_store as cds

    root = project_with_both_kinds
    ds.save_project_datasets("p1", [], root)

    assert [d.id for d in cds.load_created_datasets("p1", root)] == ["file-iris-csv"]


def test_load_project_datasets_returns_no_created_rows(project_with_both_kinds):
    # G10❌5 · negative
    # Changed: load downloaded datasets
    # Then: only `hf-x`
    # Demonstrates: download code never sees created rows
    assert [d.id for d in ds.load_project_datasets("p1", project_with_both_kinds)] == ["hf-x"]
