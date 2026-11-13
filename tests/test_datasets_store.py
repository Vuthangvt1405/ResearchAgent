"""Tests for datasets.json, dataset ids and safe paths (NB-3 plan §7: G6❌1, S❌2, S❌5, + make_id)."""

import json

import pytest

from researchchat.workspace import WorkspaceError
from researchchat.workspace import datasets_store as ds
from researchchat.workspace import store
from researchchat.workspace.dataset_pool import DatasetPool


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "workspaces"
    store.create_project("P1", root, project_id="p1")
    return root


def record(id="hf-org--name", source="huggingface", source_id="org/name", files=None, status="ready"):
    return ds.DatasetRecord(
        id=id, name=source_id, source=source, source_id=source_id, revision="r1", url=None, license="mit",
        selection=None, status=status, files=files or [ds.DatasetFile("a.csv", 3, None, True)],
    )


# ---- Group 6 — Manifest (AC28) · unit
# Baseline: Given the project has a ready dataset · When the manifest is read


def test_corrupt_manifest_is_set_aside(root):
    # G6❌1 · Changed: invalid datasets.json
    # Then: treated as empty; .bad copy kept
    # Demonstrates: a broken file never crashes the panel
    ds.save_records("p1", [record()], root)
    assert [r.id for r in ds.load_records("p1", root)] == ["hf-org--name"]

    path = ds.manifest_path("p1", root)
    path.write_text("{not json", encoding="utf-8")
    assert ds.load_records("p1", root) == []
    assert (path.parent / "datasets.json.bad").read_text(encoding="utf-8") == "{not json"
    assert not path.exists()

    path.write_text(json.dumps({"format": 1, "datasets": [{"id": "../x", "source": "huggingface", "source_id": "a"}]}))
    assert ds.load_records("p1", root) == []


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
        with pytest.raises(WorkspaceError):
            ds.partial_dir("p1", bad_id, "", root)
    for bad_path in ("../x", "a/../../x", "/etc/passwd", "a\\b", "C:/x", "a\x00b", "", "  ", ".", 5):
        with pytest.raises(WorkspaceError):
            ds.file_path("p1", "hf-org--name", bad_path, root)
    assert ds.safe_relpath("data/./train.csv") == "data/train.csv"
    inside = ds.file_path("p1", "hf-org--name", "data/train.csv", root)
    assert inside.is_relative_to(ds.dataset_dir("p1", "hf-org--name", root))
    assert sorted(p.name for p in root.iterdir()) == ["p1"]


def test_delete_ignores_tampered_manifests(root):
    # S❌5 (updated for NB-4) · Changed: record edited to files: ["../../notebook.ipynb"], pool_entry: "../x"
    # Then: only files/datasets/<id> links and the real entry handled; notebook intact
    # Demonstrates: delete can't be steered (#8, #23)
    pool = DatasetPool(root)
    pool_file = pool.pool_file_path("hf-org--name@1111111", "a.csv")
    pool_file.parent.mkdir(parents=True)
    pool_file.write_text("abc")
    folder = ds.dataset_dir("p1", "hf-org--name", root)
    folder.mkdir(parents=True)
    (folder / "a.csv").symlink_to(pool.link_target("hf-org--name@1111111", "a.csv"))
    other = ds.dataset_dir("p1", "zenodo-1", root)
    other.mkdir()
    path = ds.manifest_path("p1", root)
    path.write_text(json.dumps({"format": 2, "datasets": [
        {"id": "hf-org--name", "pool_entry": "../x", "selection": None, "status": "ready", "files": ["../../notebook.ipynb"]},
    ]}))

    [tampered] = ds.load_project_datasets("p1", root)
    pool.unlink_dataset("p1", tampered.id)
    assert pool.remove_unused_entry(tampered.pool_entry) == 0
    with pytest.raises(WorkspaceError):
        pool.entry_dir(tampered.pool_entry)

    project = store.project_dir("p1", root)
    assert (project / "notebook.ipynb").is_file()
    assert not folder.exists()
    assert other.is_dir()
    assert pool_file.read_text() == "abc"
