"""Created datasets: scan, listing, rename, missing, delete (PCD-1 plan §7).

Files are written straight into root/<project>/files/ to stand in for kernel code
(G5✅4 uses a real kernel).

Plan: docs/plans/PCD-1-created-datasets-plan.md §7
"""

import asyncio
import json
import shutil
from itertools import count

import pytest

from researchchat.config import CREATED_DATA_EXTENSIONS
from researchchat.workspace import ErrorCode, WorkspaceError, store
from researchchat.workspace import datasets_store as ds
from researchchat.workspace.created_datasets import (
    CreatedDatasets,
    compare_with_stored,
    missing_notice,
)
from researchchat.workspace.created_datasets_store import CreatedDataset, FileSnapshot
from researchchat.workspace.dataset_pool import DatasetPool, PoolEntry, PoolFile
from researchchat.workspace.dataset_service import DatasetService

IRIS_CSV = "sepal_length,species\n5.1,setosa\n4.9,setosa\n"  # 41 bytes


def run(coro):
    return asyncio.run(coro)


def ticking_clock():
    """A clock that moves one second per call, so 'newer' is checkable."""
    seconds = count()
    return lambda: f"2026-11-16T09:00:{next(seconds):02d}Z"


@pytest.fixture
def root(tmp_path):
    """A workspace with projects p and q (q is the "other project" in isolation tests)."""
    root = tmp_path / "workspaces"
    store.create_project("P", root, project_id="p")
    store.create_project("Q", root, project_id="q")
    return root


@pytest.fixture
def created(root):
    return CreatedDatasets(root, clock=ticking_clock())


@pytest.fixture
def datasets(root, created):
    return DatasetService(root=root, created=created)


def files_dir(root, project_id: str = "p"):
    return store.project_dir(project_id, root) / store.FILES_DIR


def write(root, path: str, content: str = IRIS_CSV, project_id: str = "p"):
    target = files_dir(root, project_id) / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return target


def rows(created, project_id: str = "p") -> list[dict]:
    return created.panel_rows(project_id)


def names(created, project_id: str = "p") -> list[str]:
    return [row["name"] for row in rows(created, project_id)]


def listed_iris(root, created):
    """The shared baseline of groups 3, 7, 9, 11: Iris.csv written and listed."""
    target = write(root, "Iris.csv")
    created.sync("p")
    return target


# ---- PCD-1 Group 1 — A new data file gets a card (AC1, AC2) · unit
# Baseline: Given project `p` with an empty `files/` · When `Iris.csv` is written and `sync(p)` runs


def test_new_csv_is_listed_as_created_and_ready(root, created):
    # G1✅1 · baseline
    # Changed: —
    # Then: one row: name `Iris.csv`, size, `ready`, path `/work/Iris.csv`, origin `created`
    # Demonstrates: a file saved by code becomes a dataset
    write(root, "Iris.csv")

    assert created.sync("p") is True

    [row] = rows(created)
    assert (row["id"], row["name"], row["size_bytes"], row["status"]) == ("file-iris-csv", "Iris.csv", len(IRIS_CSV), "ready")
    assert (row["path"], row["origin"], row["source"]) == ("/work/Iris.csv", "created", "created")


def test_file_in_subfolder_is_listed_with_its_folder(root, created):
    # G1✅2 · edge
    # Changed: file at `out/results.csv`
    # Then: path `/work/out/results.csv`
    # Demonstrates: data in folders isn't lost
    write(root, "out/results.csv")

    created.sync("p")

    assert [(row["name"], row["path"]) for row in rows(created)] == [("results.csv", "/work/out/results.csv")]


def test_name_with_spaces_and_quotes_is_listed(root, created):
    # G1✅3 · edge
    # Changed: file `my "iris" data.csv`
    # Then: listed, name unchanged
    # Demonstrates: odd names still show
    write(root, 'my "iris" data.csv')

    created.sync("p")

    assert names(created) == ['my "iris" data.csv']


def test_empty_csv_is_listed_with_zero_size(root, created):
    # G1✅4 · edge
    # Changed: 0-byte file
    # Then: listed, size 0
    # Demonstrates: an empty result is still visible
    write(root, "empty.csv", content="")

    created.sync("p")

    assert [row["size_bytes"] for row in rows(created)] == [0]


def test_nothing_listed_when_no_file_written(root, created):
    # G1❌1 · negative
    # Changed: no file
    # Then: no rows, no DB write
    # Demonstrates: no phantom cards
    assert created.sync("p") is False
    assert rows(created) == []


# ---- PCD-1 Group 3 — Saving again updates, never duplicates (AC4) · unit
# Baseline: Given `Iris.csv` listed · When it is rewritten bigger and `sync` runs


def test_resave_updates_size_and_keeps_one_card(root, created):
    # G3✅1 · baseline
    # Changed: —
    # Then: one row, new size, `updated_at` newer, same id
    # Demonstrates: AC4
    target = listed_iris(root, created)
    [before] = rows(created)
    target.write_text(IRIS_CSV * 3)

    assert created.sync("p") is True

    [after] = rows(created)
    assert (after["id"], after["size_bytes"]) == (before["id"], len(IRIS_CSV) * 3)
    assert after["downloaded_at"] > before["downloaded_at"]


def test_resave_many_times_in_one_turn_keeps_one_card(root, created):
    # G3✅2 · edge
    # Changed: 5 writes, then one sync
    # Then: one row
    # Demonstrates: loops don't multiply cards
    for copy_number in range(1, 6):
        write(root, "Iris.csv", IRIS_CSV * copy_number)

    created.sync("p")

    assert names(created) == ["Iris.csv"]


def test_unchanged_file_writes_nothing(root, created):
    # G3✅3 · edge
    # Changed: file not rewritten
    # Then: no DB write, rev unchanged
    # Demonstrates: scans are cheap when nothing changed
    listed_iris(root, created)
    [before] = rows(created)

    assert created.sync("p") is False
    assert rows(created) == [before]


# ---- PCD-1 Group 4 — Only data files count (AC5, A4) · unit
# Baseline: Given an empty `files/` · When `Iris.csv`, `plot.png`, `model.pkl` are written and `sync` runs


def test_only_data_files_are_listed(root, created):
    # G4✅1 · baseline
    # Changed: —
    # Then: only `Iris.csv`
    # Demonstrates: AC5
    for path in ("Iris.csv", "plot.png", "model.pkl"):
        write(root, path)

    created.sync("p")

    assert names(created) == ["Iris.csv"]


def test_every_data_extension_is_listed(root, created):
    # G4✅2 · edge
    # Changed: one file per extension in A4
    # Then: all listed
    # Demonstrates: the list in A4 is complete
    for extension in CREATED_DATA_EXTENSIONS:
        write(root, f"data{extension}")

    created.sync("p")

    assert sorted(names(created)) == sorted(f"data{extension}" for extension in CREATED_DATA_EXTENSIONS)
    assert len(CREATED_DATA_EXTENSIONS) == 9


def test_extension_match_ignores_case(root, created):
    # G4✅3 · edge
    # Changed: `IRIS.CSV`
    # Then: listed
    # Demonstrates: Windows-style names work
    write(root, "IRIS.CSV")

    created.sync("p")

    assert names(created) == ["IRIS.CSV"]


def test_image_is_not_listed(root, created):
    # G4❌1 · negative
    # Changed: only `plot.png`
    # Then: none
    # Demonstrates: images aren't datasets
    write(root, "plot.png")

    assert created.sync("p") is False
    assert rows(created) == []


def test_pickle_is_not_listed(root, created):
    # G4❌2 · negative
    # Changed: only `model.pkl`
    # Then: none
    # Demonstrates: models aren't datasets
    write(root, "model.pkl")

    created.sync("p")

    assert rows(created) == []


def test_file_without_extension_is_not_listed(root, created):
    # G4❌3 · negative
    # Changed: `data`
    # Then: none
    # Demonstrates: unknown files aren't datasets
    write(root, "data")

    created.sync("p")

    assert rows(created) == []


def test_hidden_and_checkpoint_folders_are_skipped(root, created):
    # G4❌4 · negative
    # Changed: `.ipynb_checkpoints/x.csv`, `.cache/y.csv`, `.hidden.csv`
    # Then: none
    # Demonstrates: tool clutter isn't a dataset
    for path in (".ipynb_checkpoints/x.csv", ".cache/y.csv", ".hidden.csv"):
        write(root, path)

    created.sync("p")

    assert rows(created) == []


# ---- PCD-1 Group 5 — Load code (AC6, SEC5) · docker
# Baseline: Given a real kernel for project `p` · When kernel code saves Iris.csv, the scan lists it,
#   and the card's load code runs in the same kernel


@pytest.mark.docker
def test_created_csv_load_code_runs_in_kernel(root, created):
    # G5✅4 · edge
    # Changed: real kernel (`@pytest.mark.docker`)
    # Then: runs without error, `df.shape` > 0
    # Demonstrates: the code truly works
    from researchchat.workspace.kernels import KernelRegistry

    async def noop(_output):
        pass

    async def scenario():
        kernels = KernelRegistry(root=root, timeout_seconds=60)
        try:
            save = 'import pandas as pd\npd.DataFrame({"a": [1, 2], "b": [3, 4]}).to_csv("Iris.csv", index=False)'
            assert (await kernels.execute("p", save, noop, files_dir(root))).status == "done"
            created.sync("p")
            [row] = rows(created)
            # The same code createdLoadCode builds for this card (public/panel/src/lib/loadCode.ts)
            load = f"import pandas as pd\ndf = pd.read_csv({json.dumps(row['path'])})\ndf.shape"
            return await kernels.execute("p", load, noop, files_dir(root))
        finally:
            await kernels.stop_all()

    result = run(scenario())

    assert result.status == "done"
    assert result.outputs[-1]["data"]["text/plain"] == "(2, 2)"


# ---- PCD-1 Group 6 — Only the project's own files (AC10, SEC1, SEC8) · unit
# Baseline: Given project `p` · When a file is placed as described and `sync(p)` runs


def test_regular_file_inside_files_is_listed(root, created):
    # G6✅1 · baseline
    # Changed: regular `Iris.csv`
    # Then: listed
    # Demonstrates: a plain file inside the project counts
    write(root, "Iris.csv")

    created.sync("p")

    assert names(created) == ["Iris.csv"]


def test_symlink_to_outside_file_is_not_listed(root, created, tmp_path):
    # G6❌1 · negative
    # Changed: `evil.csv → <outside>/secret.csv`
    # Then: not listed
    # Demonstrates: no escape via links
    outside_file = tmp_path / "secret.csv"
    outside_file.write_text(IRIS_CSV)
    (files_dir(root) / "evil.csv").symlink_to(outside_file)

    created.sync("p")

    assert rows(created) == []


def test_symlink_to_other_projects_file_is_not_listed(root, created):
    # G6❌2 · negative
    # Changed: link to `q/files/x.csv`
    # Then: not listed; project `q` rows unchanged
    # Demonstrates: projects stay apart
    other_file = write(root, "x.csv", project_id="q")
    (files_dir(root) / "x.csv").symlink_to(other_file)

    created.sync("p")

    assert rows(created, "p") == [] and rows(created, "q") == []


def test_symlinked_folder_is_not_walked(root, created, tmp_path):
    # G6❌3 · negative
    # Changed: `out → <outside folder>` containing CSVs
    # Then: nothing listed
    # Demonstrates: folders behind links are skipped
    outside_folder = tmp_path / "outside"
    outside_folder.mkdir()
    (outside_folder / "a.csv").write_text(IRIS_CSV)
    (files_dir(root) / "out").symlink_to(outside_folder, target_is_directory=True)

    created.sync("p")

    assert rows(created) == []


def test_symlink_inside_files_is_not_listed(root, created):
    # G6❌4 · negative
    # Changed: `b.csv → a.csv` (both inside)
    # Then: only `a.csv`
    # Demonstrates: one rule for all links, simpler and safe
    real_file = write(root, "a.csv")
    (files_dir(root) / "b.csv").symlink_to(real_file)

    created.sync("p")

    assert names(created) == ["a.csv"]


def test_pool_links_are_not_listed_as_created(root, created):
    # G6❌5 · negative
    # Changed: CSV under `files/datasets/hf-x/`
    # Then: not created; downloaded card unchanged
    # Demonstrates: no duplicates with downloads
    write(root, "datasets/hf-x/train.csv")
    write(root, "results/datasets/kept.csv")  # only the top-level datasets/ folder is the pool's

    created.sync("p")

    assert names(created) == ["kept.csv"]


def test_other_project_is_not_scanned(root, created):
    # G6❌6 · negative
    # Changed: write in `q/files/` and sync `p`
    # Then: no rows for either
    # Demonstrates: scan scope is one project
    write(root, "x.csv", project_id="q")

    created.sync("p")

    assert rows(created, "p") == [] and rows(created, "q") == []


# ---- PCD-1 Group 7 — Missing (AC7, AC11) · unit
# Baseline: Given `Iris.csv` listed · When the file is removed and the list is read


def test_deleted_file_shows_missing(root, created, datasets):
    # G7✅1 · baseline
    # Changed: —
    # Then: card `missing`; `dataset_list` `missing`, `missing_files` = `[/work/Iris.csv]`
    # Demonstrates: AC7
    listed_iris(root, created).unlink()

    [row] = rows(created)
    [view] = datasets.list_for_model("p")
    assert row["status"] == "missing"
    assert (view["status"], view["missing_files"], view["origin"]) == ("missing", ["/work/Iris.csv"], "created")


def test_file_back_at_same_path_is_ready_again(root, created):
    # G7✅2 · edge
    # Changed: file recreated
    # Then: `ready`, same id
    # Demonstrates: no stuck missing
    listed_iris(root, created).unlink()
    write(root, "Iris.csv")

    created.sync("p")

    assert [(row["id"], row["status"]) for row in rows(created)] == [("file-iris-csv", "ready")]


def test_missing_file_is_not_dropped_by_scan(root, created):
    # G7❌3 · negative
    # Changed: sync after delete
    # Then: row kept
    # Demonstrates: card stays until the user deletes it
    listed_iris(root, created).unlink()

    created.sync("p")

    assert [(row["name"], row["status"]) for row in rows(created)] == [("Iris.csv", "missing")]
    assert created.missing_names("p") == ["Iris.csv"]


def test_file_replaced_by_link_shows_missing(root, created, tmp_path):
    # G7❌4 · negative
    # Changed: `Iris.csv` replaced by a link
    # Then: `missing`
    # Demonstrates: a link never counts as the file
    target = listed_iris(root, created)
    outside_file = tmp_path / "other.csv"
    outside_file.write_text(IRIS_CSV)
    target.unlink()
    target.symlink_to(outside_file)

    created.sync("p")

    assert [row["status"] for row in rows(created)] == ["missing"]


# ---- PCD-1 Group 8 — One list, two kinds (AC3, AC9) · unit
# Baseline: Given downloaded `hf-scikit-learn--iris` and created `Iris.csv` · When `panel_state` / `list_for_model` run


def test_panel_state_has_both_kinds_in_one_list(root, created, datasets):
    # G8✅1 · baseline
    # Changed: —
    # Then: 2 rows, origins `downloaded` and `created`
    # Demonstrates: AC3
    pool = DatasetPool(root)
    pool.add_entry(PoolEntry("hf-scikit-learn--iris", "huggingface", "scikit-learn/iris", None, "iris", None, "cc0",
                             [PoolFile("Iris.csv", 10, None, True)]))
    pool.save_index()
    ds.save_project_datasets("p", [ds.ProjectDataset("hf-scikit-learn--iris", "hf-scikit-learn--iris", None, "ready", ["Iris.csv"])], root)
    listed_iris(root, created)

    panel_rows, _rev = datasets.panel_state("p")

    assert [(row["id"], row["origin"]) for row in panel_rows] == [
        ("hf-scikit-learn--iris", "downloaded"), ("file-iris-csv", "created"),
    ]


def test_created_id_never_clashes_with_catalog_id(root, created):
    # G8❌1 · negative
    # Changed: created `hf.csv`, and two names with the same slug
    # Then: id `file-hf-csv`; the second gets `-2`
    # Demonstrates: Delete hits the right one
    write(root, "hf.csv")
    write(root, "HF.csv")

    created.sync("p")

    assert sorted(row["id"] for row in rows(created)) == ["file-hf-csv", "file-hf-csv-2"]


def test_long_file_name_is_capped_in_views(root, created, datasets):
    # G8❌2 · negative
    # Changed: 250-char name (filesystems stop at 255)
    # Then: name ≤ 200
    # Demonstrates: the tab and model aren't flooded
    write(root, "x" * 246 + ".csv")

    created.sync("p")

    assert len(rows(created)[0]["name"]) == ds.NAME_MAX
    assert len(datasets.list_for_model("p")[0]["name"]) == ds.NAME_MAX


# ---- PCD-1 Group 9 — Delete warns and removes only the file (AC8, AC13) · unit
# Baseline: Given created `Iris.csv` listed · When `ds_delete file-iris-csv` runs (DatasetService.delete)


def test_delete_created_removes_file_and_row(root, created, datasets):
    # G9✅1 · baseline
    # Changed: —
    # Then: file gone, row gone, rev bumped
    # Demonstrates: AC8 Confirm
    target = listed_iris(root, created)
    rev_before = datasets.rev

    result = run(datasets.delete("p", "file-iris-csv"))

    assert not target.exists() and rows(created) == []
    assert result == {"deleted": "file-iris-csv", "freed_bytes": len(IRIS_CSV), "still_used_by": 0}
    assert datasets.rev == rev_before + 1


def test_delete_missing_created_removes_card(root, created, datasets):
    # G9✅4 · edge
    # Changed: file already gone
    # Then: row gone, no error
    # Demonstrates: user can clear a missing card
    listed_iris(root, created).unlink()

    run(datasets.delete("p", "file-iris-csv"))

    assert rows(created) == []


def test_file_saved_again_after_delete_gets_new_card(root, created, datasets):
    # G9✅5 · edge
    # Changed: after delete, code saves `Iris.csv` again, then sync
    # Then: one new `ready` card
    # Demonstrates: AC13
    listed_iris(root, created)
    run(datasets.delete("p", "file-iris-csv"))
    write(root, "Iris.csv")

    created.sync("p")

    assert [(row["name"], row["status"]) for row in rows(created)] == [("Iris.csv", "ready")]


def test_delete_unknown_id_is_not_found(root, created, datasets):
    # G9❌1 · negative
    # Changed: id `file-nope`
    # Then: `NOT_FOUND`, nothing changed
    # Demonstrates: unknown ids are refused
    target = listed_iris(root, created)

    with pytest.raises(WorkspaceError) as refused:
        run(datasets.delete("p", "file-nope"))

    assert refused.value.code == ErrorCode.NOT_FOUND
    assert target.exists() and names(created) == ["Iris.csv"]


def test_delete_created_does_not_touch_other_files(root, created, datasets):
    # G9❌2 · negative
    # Changed: sibling `Iris2.csv`
    # Then: sibling still there
    # Demonstrates: delete is exact
    listed_iris(root, created)
    sibling = write(root, "Iris2.csv")
    created.sync("p")

    run(datasets.delete("p", "file-iris-csv"))

    assert sibling.exists() and names(created) == ["Iris2.csv"]


# ---- PCD-1 Group 11 — A rename keeps the card (AC12, SEC10) · unit
# Baseline: Given `Iris.csv` listed as `file-iris-csv` · When it is renamed to `iris_v2.csv` (contents unchanged) and `sync` runs


def test_renamed_file_keeps_its_card_with_new_name(root, created):
    # G11✅1 · baseline
    # Changed: —
    # Then: one row, id `file-iris-csv`, name `iris_v2.csv`, path `/work/iris_v2.csv`, `ready`; no `missing` row
    # Demonstrates: AC12
    target = listed_iris(root, created)
    target.rename(target.with_name("iris_v2.csv"))

    assert created.sync("p") is True

    assert [(row["id"], row["name"], row["path"], row["status"]) for row in rows(created)] == [
        ("file-iris-csv", "iris_v2.csv", "/work/iris_v2.csv", "ready"),
    ]


def test_file_moved_into_subfolder_keeps_its_card(root, created):
    # G11✅2 · edge
    # Changed: moved to `out/Iris.csv`
    # Then: same id, path `/work/out/Iris.csv`
    # Demonstrates: moves count as renames
    target = listed_iris(root, created)
    (target.parent / "out").mkdir()
    target.rename(target.parent / "out" / "Iris.csv")

    created.sync("p")

    assert [(row["id"], row["path"]) for row in rows(created)] == [("file-iris-csv", "/work/out/Iris.csv")]


def test_renamed_file_gets_no_toast(root, created):
    # G11✅3 · edge
    # Changed: then the workspace is opened
    # Then: no missing names, so no toast
    # Demonstrates: a rename isn't a loss
    target = listed_iris(root, created)
    target.rename(target.with_name("iris_v2.csv"))
    created.sync("p")

    assert created.missing_names("p") == []


def test_rename_to_non_data_name_shows_missing(root, created):
    # G11❌1 · negative
    # Changed: renamed to `iris.txt`
    # Then: card `missing`, no new card
    # Demonstrates: AC5 still applies
    target = listed_iris(root, created)
    target.rename(target.with_name("iris.txt"))

    created.sync("p")

    assert [(row["name"], row["status"]) for row in rows(created)] == [("Iris.csv", "missing")]


def test_move_into_hidden_folder_shows_missing(root, created):
    # G11❌2 · negative
    # Changed: moved to `.old/Iris.csv`
    # Then: card `missing`
    # Demonstrates: skipped folders still skipped
    target = listed_iris(root, created)
    (target.parent / ".old").mkdir()
    target.rename(target.parent / ".old" / "Iris.csv")

    created.sync("p")

    assert [(row["path"], row["status"]) for row in rows(created)] == [("/work/Iris.csv", "missing")]


def test_copy_keeps_original_and_adds_card(root, created):
    # G11❌3 · negative
    # Changed: copied with its mtime (new inode), original kept
    # Then: original `ready`, copy gets its own card
    # Demonstrates: a copy isn't a rename
    target = listed_iris(root, created)
    shutil.copy2(target, target.with_name("copy.csv"))

    created.sync("p")

    assert sorted((row["name"], row["status"]) for row in rows(created)) == [("Iris.csv", "ready"), ("copy.csv", "ready")]


def test_rename_and_edit_in_one_run_is_missing_plus_new_card(root, created):
    # G11❌4 · negative
    # Changed: renamed and rewritten before sync
    # Then: old `missing`, new card
    # Demonstrates: unmatched renames fall back to AC7
    target = listed_iris(root, created)
    renamed = target.rename(target.with_name("iris_v2.csv"))
    renamed.write_text(IRIS_CSV * 2)

    created.sync("p")

    assert sorted((row["name"], row["status"]) for row in rows(created)) == [("Iris.csv", "missing"), ("iris_v2.csv", "ready")]


def test_new_file_on_reused_inode_is_not_a_rename():
    # G11❌5 · negative
    # Changed: old file deleted, new file reuses its inode with another mtime
    # Then: old `missing`, new card
    # Demonstrates: a stranger can't take over a card (SEC10)
    gone = CreatedDataset("file-iris-csv", FileSnapshot("Iris.csv", 41, 1_000, inode=7), "t", "t")
    stranger = FileSnapshot("other.csv", 41, 2_000, inode=7)

    changes = compare_with_stored([gone], [stranger])

    assert (changes.new_files, changes.renamed, changes.resaved) == ([stranger], [], [])


# ---- PCD-1 Group S1 — Delete never follows links (SEC1, SEC2) · unit
# Baseline: Given created `Iris.csv` listed, and a victim file outside `files/` · When `ds_delete` runs after the change below


@pytest.fixture
def victim(tmp_path):
    victim_file = tmp_path / "victim" / "x.csv"
    victim_file.parent.mkdir()
    victim_file.write_text("keep me")
    return victim_file


def test_delete_when_file_became_link_keeps_target(root, created, datasets, victim):
    # S1❌1 · negative
    # Changed: `Iris.csv` replaced by link → victim
    # Then: victim intact; link and row removed
    # Demonstrates: Delete can't destroy outside files
    target = listed_iris(root, created)
    target.unlink()
    target.symlink_to(victim)

    run(datasets.delete("p", "file-iris-csv"))

    assert victim.read_text() == "keep me"
    assert not target.is_symlink() and rows(created) == []


def test_delete_when_parent_folder_became_link_keeps_target(root, created, datasets, victim):
    # S1❌2 · negative
    # Changed: `out/` replaced by link, row `out/x.csv`
    # Then: victim intact; row removed
    # Demonstrates: folder links too
    listed = write(root, "out/x.csv")
    created.sync("p")
    listed.unlink()
    listed.parent.rmdir()
    listed.parent.symlink_to(victim.parent, target_is_directory=True)

    run(datasets.delete("p", "file-out-x-csv"))

    assert victim.read_text() == "keep me" and rows(created) == []


def test_delete_link_to_other_project_keeps_its_file(root, created, datasets):
    # S1❌3 · negative
    # Changed: link → `q/files/x.csv`
    # Then: `q`'s file intact
    # Demonstrates: projects can't harm each other
    other_file = write(root, "x.csv", project_id="q")
    target = listed_iris(root, created)
    target.unlink()
    target.symlink_to(other_file)

    run(datasets.delete("p", "file-iris-csv"))

    assert other_file.read_text() == IRIS_CSV


def test_delete_holds_run_lock(root):
    # S1❌4 · negative
    # Changed: a run is in progress
    # Then: delete waits until the run ends
    # Demonstrates: no swap between check and unlink
    run_lock = asyncio.Lock()
    created = CreatedDatasets(root, run_lock=lambda project_id: run_lock)
    target = write(root, "Iris.csv")
    created.sync("p")

    async def scenario():
        await run_lock.acquire()  # a cell is running
        deleting = asyncio.create_task(created.delete("p", "file-iris-csv"))
        await asyncio.sleep(0.05)
        waited = not deleting.done() and target.exists()
        run_lock.release()
        await deleting
        return waited

    assert run(scenario()) is True
    assert not target.exists()


# ---- PCD-1 Group S3 — Names are shown as text (SEC6) · unit
# Baseline: negatives only (injection payloads), no baseline row


def test_toast_strips_newlines_and_caps_names():
    # S3❌2 · negative
    # Changed: name with `\n`, control characters, 300 chars
    # Then: one line, name ≤ 80 chars
    # Demonstrates: toast text can't be broken or flooded
    notice = missing_notice(["evil\nname\x1b[31m.csv", "y" * 300 + ".csv"])

    assert "\n" not in notice and "\x1b" not in notice
    assert "evilname[31m.csv" in notice
    assert "y" * 79 + "…" in notice and "y" * 80 not in notice
