"""Created datasets: scan, listing, rename, missing, delete.

Files are written straight into root/<project>/files/ to stand in for kernel code
(the load-code test uses a real kernel).
"""

import asyncio
import gzip
import json
import os
import shutil
import time
from itertools import count

import openpyxl
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from openpyxl.worksheet._read_only import ReadOnlyWorksheet

from researchchat.config import CREATED_DATA_EXTENSIONS
from researchchat.workspace import ErrorCode, WorkspaceError, store
from researchchat.workspace.datasets import created as created_module
from researchchat.workspace.datasets import created_store as cds
from researchchat.workspace.datasets import store as ds
from researchchat.workspace.datasets.created import (
    CreatedDatasets,
    compare_with_stored,
    missing_notice,
    read_columns,
)
from researchchat.workspace.datasets.created_store import CreatedDataset, FileSnapshot
from researchchat.workspace.datasets.pool import DatasetPool, PoolEntry, PoolFile
from researchchat.workspace.datasets.service import DatasetService

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


# ---- A new data file gets a card · unit
# Baseline: Given project `p` with an empty `files/` · When `Iris.csv` is written and `sync(p)` runs


def test_new_csv_is_listed_as_created_and_ready(root, created):
    # baseline
    # Changed: —
    # Then: one row: name `Iris.csv`, size, `ready`, path `/work/Iris.csv`, origin `created`
    # Demonstrates: a file saved by code becomes a dataset
    write(root, "Iris.csv")

    assert created.sync("p") is True

    [row] = rows(created)
    assert (row["id"], row["name"], row["size_bytes"], row["status"]) == ("file-iris-csv", "Iris.csv", len(IRIS_CSV), "ready")
    assert (row["path"], row["origin"], row["source"]) == ("/work/Iris.csv", "created", "created")


def test_file_in_subfolder_is_listed_with_its_folder(root, created):
    # edge
    # Changed: file at `out/results.csv`
    # Then: path `/work/out/results.csv`
    # Demonstrates: data in folders isn't lost
    write(root, "out/results.csv")

    created.sync("p")

    assert [(row["name"], row["path"]) for row in rows(created)] == [("results.csv", "/work/out/results.csv")]


def test_name_with_spaces_and_quotes_is_listed(root, created):
    # edge
    # Changed: file `my "iris" data.csv`
    # Then: listed, name unchanged
    # Demonstrates: odd names still show
    write(root, 'my "iris" data.csv')

    created.sync("p")

    assert names(created) == ['my "iris" data.csv']


def test_empty_csv_is_listed_with_zero_size(root, created):
    # edge
    # Changed: 0-byte file
    # Then: listed, size 0
    # Demonstrates: an empty result is still visible
    write(root, "empty.csv", content="")

    created.sync("p")

    assert [row["size_bytes"] for row in rows(created)] == [0]


def test_nothing_listed_when_no_file_written(root, created):
    # negative
    # Changed: no file
    # Then: no rows, no DB write
    # Demonstrates: no phantom cards
    assert created.sync("p") is False
    assert rows(created) == []


# ---- Saving again updates, never duplicates · unit
# Baseline: Given `Iris.csv` listed · When it is rewritten bigger and `sync` runs


def test_resave_updates_size_and_keeps_one_card(root, created):
    # baseline
    # Changed: —
    # Then: one row, new size, `updated_at` newer, same id
    target = listed_iris(root, created)
    [before] = rows(created)
    target.write_text(IRIS_CSV * 3)

    assert created.sync("p") is True

    [after] = rows(created)
    assert (after["id"], after["size_bytes"]) == (before["id"], len(IRIS_CSV) * 3)
    assert after["downloaded_at"] > before["downloaded_at"]


def test_resave_many_times_in_one_turn_keeps_one_card(root, created):
    # edge
    # Changed: 5 writes, then one sync
    # Then: one row
    # Demonstrates: loops don't multiply cards
    for copy_number in range(1, 6):
        write(root, "Iris.csv", IRIS_CSV * copy_number)

    created.sync("p")

    assert names(created) == ["Iris.csv"]


def test_unchanged_file_writes_nothing(root, created):
    # edge
    # Changed: file not rewritten
    # Then: no DB write, rev unchanged
    # Demonstrates: scans are cheap when nothing changed
    listed_iris(root, created)
    [before] = rows(created)

    assert created.sync("p") is False
    assert rows(created) == [before]


# ---- Only data files count · unit
# Baseline: Given an empty `files/` · When `Iris.csv`, `plot.png`, `model.pkl` are written and `sync` runs


def test_only_data_files_are_listed(root, created):
    # baseline
    # Changed: —
    # Then: only `Iris.csv`
    for path in ("Iris.csv", "plot.png", "model.pkl"):
        write(root, path)

    created.sync("p")

    assert names(created) == ["Iris.csv"]


def test_every_data_extension_is_listed(root, created):
    # edge
    # Changed: one file per data extension
    # Then: all listed
    # Demonstrates: the data-extension list is complete
    for extension in CREATED_DATA_EXTENSIONS:
        write(root, f"data{extension}")

    created.sync("p")

    assert sorted(names(created)) == sorted(f"data{extension}" for extension in CREATED_DATA_EXTENSIONS)
    assert len(CREATED_DATA_EXTENSIONS) == 9


def test_extension_match_ignores_case(root, created):
    # edge
    # Changed: `IRIS.CSV`
    # Then: listed
    # Demonstrates: Windows-style names work
    write(root, "IRIS.CSV")

    created.sync("p")

    assert names(created) == ["IRIS.CSV"]


def test_image_is_not_listed(root, created):
    # negative
    # Changed: only `plot.png`
    # Then: none
    # Demonstrates: images aren't datasets
    write(root, "plot.png")

    assert created.sync("p") is False
    assert rows(created) == []


def test_pickle_is_not_listed(root, created):
    # negative
    # Changed: only `model.pkl`
    # Then: none
    # Demonstrates: models aren't datasets
    write(root, "model.pkl")

    created.sync("p")

    assert rows(created) == []


def test_file_without_extension_is_not_listed(root, created):
    # negative
    # Changed: `data`
    # Then: none
    # Demonstrates: unknown files aren't datasets
    write(root, "data")

    created.sync("p")

    assert rows(created) == []


def test_hidden_and_checkpoint_folders_are_skipped(root, created):
    # negative
    # Changed: `.ipynb_checkpoints/x.csv`, `.cache/y.csv`, `.hidden.csv`
    # Then: none
    # Demonstrates: tool clutter isn't a dataset
    for path in (".ipynb_checkpoints/x.csv", ".cache/y.csv", ".hidden.csv"):
        write(root, path)

    created.sync("p")

    assert rows(created) == []


# ---- Load code · docker
# Baseline: Given a real kernel for project `p` · When kernel code saves Iris.csv, the scan lists it,
#   and the card's load code runs in the same kernel


@pytest.mark.docker
def test_created_csv_load_code_runs_in_kernel(root, created):
    # edge
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


# ---- Only the project's own files · unit
# Baseline: Given project `p` · When a file is placed as described and `sync(p)` runs


def test_regular_file_inside_files_is_listed(root, created):
    # baseline
    # Changed: regular `Iris.csv`
    # Then: listed
    # Demonstrates: a plain file inside the project counts
    write(root, "Iris.csv")

    created.sync("p")

    assert names(created) == ["Iris.csv"]


def test_symlink_to_outside_file_is_not_listed(root, created, tmp_path):
    # negative
    # Changed: `evil.csv → <outside>/secret.csv`
    # Then: not listed
    # Demonstrates: no escape via links
    outside_file = tmp_path / "secret.csv"
    outside_file.write_text(IRIS_CSV)
    (files_dir(root) / "evil.csv").symlink_to(outside_file)

    created.sync("p")

    assert rows(created) == []


def test_symlink_to_other_projects_file_is_not_listed(root, created):
    # negative
    # Changed: link to `q/files/x.csv`
    # Then: not listed; project `q` rows unchanged
    # Demonstrates: projects stay apart
    other_file = write(root, "x.csv", project_id="q")
    (files_dir(root) / "x.csv").symlink_to(other_file)

    created.sync("p")

    assert rows(created, "p") == [] and rows(created, "q") == []


def test_symlinked_folder_is_not_walked(root, created, tmp_path):
    # negative
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
    # negative
    # Changed: `b.csv → a.csv` (both inside)
    # Then: only `a.csv`
    # Demonstrates: one rule for all links, simpler and safe
    real_file = write(root, "a.csv")
    (files_dir(root) / "b.csv").symlink_to(real_file)

    created.sync("p")

    assert names(created) == ["a.csv"]


def test_pool_links_are_not_listed_as_created(root, created):
    # negative
    # Changed: CSV under `files/datasets/hf-x/`
    # Then: not created; downloaded card unchanged
    # Demonstrates: no duplicates with downloads
    write(root, "datasets/hf-x/train.csv")
    write(root, "results/datasets/kept.csv")  # only the top-level datasets/ folder is the pool's

    created.sync("p")

    assert names(created) == ["kept.csv"]


def test_other_project_is_not_scanned(root, created):
    # negative
    # Changed: write in `q/files/` and sync `p`
    # Then: no rows for either
    # Demonstrates: scan scope is one project
    write(root, "x.csv", project_id="q")

    created.sync("p")

    assert rows(created, "p") == [] and rows(created, "q") == []


# ---- Missing · unit
# Baseline: Given `Iris.csv` listed · When the file is removed and the list is read


def test_deleted_file_shows_missing(root, created, datasets):
    # baseline
    # Changed: —
    # Then: card `missing`; `dataset_list` `missing`, `missing_files` = `[/work/Iris.csv]`
    listed_iris(root, created).unlink()

    [row] = rows(created)
    [view] = datasets.list_for_model("p")
    assert row["status"] == "missing"
    assert (view["status"], view["missing_files"], view["origin"]) == ("missing", ["/work/Iris.csv"], "created")


def test_file_back_at_same_path_is_ready_again(root, created):
    # edge
    # Changed: file recreated
    # Then: `ready`, same id
    # Demonstrates: no stuck missing
    listed_iris(root, created).unlink()
    write(root, "Iris.csv")

    created.sync("p")

    assert [(row["id"], row["status"]) for row in rows(created)] == [("file-iris-csv", "ready")]


def test_missing_file_is_not_dropped_by_scan(root, created):
    # negative
    # Changed: sync after delete
    # Then: row kept
    # Demonstrates: card stays until the user deletes it
    listed_iris(root, created).unlink()

    created.sync("p")

    assert [(row["name"], row["status"]) for row in rows(created)] == [("Iris.csv", "missing")]
    assert created.missing_names("p") == ["Iris.csv"]


def test_file_replaced_by_link_shows_missing(root, created, tmp_path):
    # negative
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


# ---- One list, two kinds · unit
# Baseline: Given downloaded `hf-scikit-learn--iris` and created `Iris.csv` · When `panel_state` / `list_for_model` run


def test_panel_state_has_both_kinds_in_one_list(root, created, datasets):
    # baseline
    # Changed: —
    # Then: 2 rows, origins `downloaded` and `created`
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
    # negative
    # Changed: created `hf.csv`, and two names with the same slug
    # Then: id `file-hf-csv`; the second gets `-2`
    # Demonstrates: Delete hits the right one
    write(root, "hf.csv")
    write(root, "HF.csv")

    created.sync("p")

    assert sorted(row["id"] for row in rows(created)) == ["file-hf-csv", "file-hf-csv-2"]


def test_long_file_name_is_capped_in_views(root, created, datasets):
    # negative
    # Changed: 250-char name (filesystems stop at 255)
    # Then: name ≤ 200
    # Demonstrates: the tab and model aren't flooded
    write(root, "x" * 246 + ".csv")

    created.sync("p")

    assert len(rows(created)[0]["name"]) == ds.NAME_MAX
    assert len(datasets.list_for_model("p")[0]["name"]) == ds.NAME_MAX


# ---- Delete warns and removes only the file · unit
# Baseline: Given created `Iris.csv` listed · When `ds_delete file-iris-csv` runs (DatasetService.delete)


def test_delete_created_removes_file_and_row(root, created, datasets):
    # baseline
    # Changed: —
    # Then: file gone, row gone, rev bumped
    # Demonstrates: Confirm deletes the file and its card
    target = listed_iris(root, created)
    rev_before = datasets.rev

    result = run(datasets.delete("p", "file-iris-csv"))

    assert not target.exists() and rows(created) == []
    assert result == {"deleted": "file-iris-csv", "freed_bytes": len(IRIS_CSV), "still_used_by": 0}
    assert datasets.rev == rev_before + 1


def test_delete_missing_created_removes_card(root, created, datasets):
    # edge
    # Changed: file already gone
    # Then: row gone, no error
    # Demonstrates: user can clear a missing card
    listed_iris(root, created).unlink()

    run(datasets.delete("p", "file-iris-csv"))

    assert rows(created) == []


def test_file_saved_again_after_delete_gets_new_card(root, created, datasets):
    # edge
    # Changed: after delete, code saves `Iris.csv` again, then sync
    # Then: one new `ready` card
    listed_iris(root, created)
    run(datasets.delete("p", "file-iris-csv"))
    write(root, "Iris.csv")

    created.sync("p")

    assert [(row["name"], row["status"]) for row in rows(created)] == [("Iris.csv", "ready")]


def test_delete_unknown_id_is_not_found(root, created, datasets):
    # negative
    # Changed: id `file-nope`
    # Then: `NOT_FOUND`, nothing changed
    # Demonstrates: unknown ids are refused
    target = listed_iris(root, created)

    with pytest.raises(WorkspaceError) as refused:
        run(datasets.delete("p", "file-nope"))

    assert refused.value.code == ErrorCode.NOT_FOUND
    assert target.exists() and names(created) == ["Iris.csv"]


def test_delete_created_does_not_touch_other_files(root, created, datasets):
    # negative
    # Changed: sibling `Iris2.csv`
    # Then: sibling still there
    # Demonstrates: delete is exact
    listed_iris(root, created)
    sibling = write(root, "Iris2.csv")
    created.sync("p")

    run(datasets.delete("p", "file-iris-csv"))

    assert sibling.exists() and names(created) == ["Iris2.csv"]


# ---- A rename keeps the card · unit
# Baseline: Given `Iris.csv` listed as `file-iris-csv` · When it is renamed to `iris_v2.csv` (contents unchanged) and `sync` runs


def test_renamed_file_keeps_its_card_with_new_name(root, created):
    # baseline
    # Changed: —
    # Then: one row, id `file-iris-csv`, name `iris_v2.csv`, path `/work/iris_v2.csv`, `ready`; no `missing` row
    target = listed_iris(root, created)
    target.rename(target.with_name("iris_v2.csv"))

    assert created.sync("p") is True

    assert [(row["id"], row["name"], row["path"], row["status"]) for row in rows(created)] == [
        ("file-iris-csv", "iris_v2.csv", "/work/iris_v2.csv", "ready"),
    ]


def test_file_moved_into_subfolder_keeps_its_card(root, created):
    # edge
    # Changed: moved to `out/Iris.csv`
    # Then: same id, path `/work/out/Iris.csv`
    # Demonstrates: moves count as renames
    target = listed_iris(root, created)
    (target.parent / "out").mkdir()
    target.rename(target.parent / "out" / "Iris.csv")

    created.sync("p")

    assert [(row["id"], row["path"]) for row in rows(created)] == [("file-iris-csv", "/work/out/Iris.csv")]


def test_renamed_file_gets_no_toast(root, created):
    # edge
    # Changed: then the workspace is opened
    # Then: no missing names, so no toast
    # Demonstrates: a rename isn't a loss
    target = listed_iris(root, created)
    target.rename(target.with_name("iris_v2.csv"))
    created.sync("p")

    assert created.missing_names("p") == []


def test_rename_to_non_data_name_shows_missing(root, created):
    # negative
    # Changed: renamed to `iris.txt`
    # Then: card `missing`, no new card
    # Demonstrates: renaming to a non-data extension drops the card
    target = listed_iris(root, created)
    target.rename(target.with_name("iris.txt"))

    created.sync("p")

    assert [(row["name"], row["status"]) for row in rows(created)] == [("Iris.csv", "missing")]


def test_move_into_hidden_folder_shows_missing(root, created):
    # negative
    # Changed: moved to `.old/Iris.csv`
    # Then: card `missing`
    # Demonstrates: skipped folders still skipped
    target = listed_iris(root, created)
    (target.parent / ".old").mkdir()
    target.rename(target.parent / ".old" / "Iris.csv")

    created.sync("p")

    assert [(row["path"], row["status"]) for row in rows(created)] == [("/work/Iris.csv", "missing")]


def test_copy_keeps_original_and_adds_card(root, created):
    # negative
    # Changed: copied with its mtime (new inode), original kept
    # Then: original `ready`, copy gets its own card
    # Demonstrates: a copy isn't a rename
    target = listed_iris(root, created)
    shutil.copy2(target, target.with_name("copy.csv"))

    created.sync("p")

    assert sorted((row["name"], row["status"]) for row in rows(created)) == [("Iris.csv", "ready"), ("copy.csv", "ready")]


def test_rename_and_edit_in_one_run_is_missing_plus_new_card(root, created):
    # negative
    # Changed: renamed and rewritten before sync
    # Then: old `missing`, new card
    # Demonstrates: unmatched renames fall back to missing
    target = listed_iris(root, created)
    renamed = target.rename(target.with_name("iris_v2.csv"))
    renamed.write_text(IRIS_CSV * 2)

    created.sync("p")

    assert sorted((row["name"], row["status"]) for row in rows(created)) == [("Iris.csv", "missing"), ("iris_v2.csv", "ready")]


def test_new_file_on_reused_inode_is_not_a_rename():
    # negative
    # Changed: old file deleted, new file reuses its inode with another mtime
    # Then: old `missing`, new card
    # Demonstrates: a stranger can't take over a card
    gone = CreatedDataset("file-iris-csv", FileSnapshot("Iris.csv", 41, 1_000, inode=7), "t", "t")
    stranger = FileSnapshot("other.csv", 41, 2_000, inode=7)

    changes = compare_with_stored([gone], [stranger])

    assert (changes.new_files, changes.renamed, changes.resaved) == ([stranger], [], [])


# ---- Delete never follows links · unit
# Baseline: Given created `Iris.csv` listed, and a victim file outside `files/` · When `ds_delete` runs after the change below


@pytest.fixture
def victim(tmp_path):
    victim_file = tmp_path / "victim" / "x.csv"
    victim_file.parent.mkdir()
    victim_file.write_text("keep me")
    return victim_file


def test_delete_when_file_became_link_keeps_target(root, created, datasets, victim):
    # negative
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
    # negative
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
    # negative
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
    # negative
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


# ---- Names are shown as text · unit
# Baseline: negatives only (injection payloads), no baseline row


def test_toast_strips_newlines_and_caps_names():
    # negative
    # Changed: name with `\n`, control characters, 300 chars
    # Then: one line, name ≤ 80 chars
    # Demonstrates: toast text can't be broken or flooded
    notice = missing_notice(["evil\nname\x1b[31m.csv", "y" * 300 + ".csv"])

    assert "\n" not in notice and "\x1b" not in notice
    assert "evilname[31m.csv" in notice
    assert "y" * 79 + "…" in notice and "y" * 80 not in notice


# ---- PCD-4 Group 7 — Created files get their column names  (Q4 option 2; AC2, AC6) · unit (real tmp folder)
# Plan: docs/plans/PCD-4-reuse-existing-dataset-plan.md §7
# Baseline: Given a new `files/data.csv` with an iris header · When the scan runs

IRIS_COLUMNS = ["sepal_length", "sepal_width", "petal_length", "petal_width", "species"]
IRIS_HEADER = ",".join(IRIS_COLUMNS) + "\n5.1,3.5,1.4,0.2,setosa\n"


def stored_columns(created, project_id: str = "p") -> dict[str, list[str] | None]:
    """path -> stored columns of the project's created rows."""
    return {d.snapshot.path: d.columns for d in cds.load_created_datasets(project_id, created.root)}


def write_bytes(root, path: str, data: bytes):
    target = files_dir(root) / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def opened_paths(monkeypatch) -> list[str]:
    """Spy on read_columns: the paths the scan asked it to read."""
    asked: list[str] = []
    real = created_module.read_columns

    def spy(folder, path):
        asked.append(path)
        return real(folder, path)

    monkeypatch.setattr(created_module, "read_columns", spy)
    return asked


def test_csv_header_is_stored_as_columns(root, created, datasets):
    # ✅1 · Changed: —
    # Then: five names stored and listed
    write(root, "data.csv", IRIS_HEADER)
    created.sync("p")
    assert stored_columns(created) == {"data.csv": IRIS_COLUMNS}
    [view] = datasets.list_for_model("p")
    assert view["columns"] == IRIS_COLUMNS


def test_tsv_and_csv_gz_headers_are_read(root, created):
    # ✅2 · Changed: `.tsv`, `.csv.gz`
    # Then: same
    write(root, "data.tsv", IRIS_HEADER.replace(",", "\t"))
    write_bytes(root, "data.csv.gz", gzip.compress(IRIS_HEADER.encode()))
    write_bytes(root, "data.tsv.gz", gzip.compress(IRIS_HEADER.replace(",", "\t").encode()))
    created.sync("p")
    assert stored_columns(created) == {"data.csv.gz": IRIS_COLUMNS, "data.tsv": IRIS_COLUMNS, "data.tsv.gz": IRIS_COLUMNS}


def test_json_and_jsonl_first_record_keys_are_read(root, created):
    # ✅3 · Changed: `.jsonl`, `.json`
    # Then: first record's keys
    record = dict.fromkeys(IRIS_COLUMNS, 1)
    write(root, "rows.jsonl", json.dumps(record) + "\n" + json.dumps({"other": 2}) + "\n")
    write(root, "rows.json", json.dumps([record, {"other": 2}], indent=2))
    created.sync("p")
    assert stored_columns(created) == {"rows.json": IRIS_COLUMNS, "rows.jsonl": IRIS_COLUMNS}


def test_quoted_header_cells_are_unquoted(root, created):
    # ✅4 · Changed: quoted cells
    # Then: unquoted names
    write(root, "q.csv", '﻿"sepal length","species, name"\n1,a\n')
    created.sync("p")
    assert stored_columns(created) == {"q.csv": ["sepal length", "species, name"]}


def test_resaved_file_with_new_header_updates_columns(root, created):
    # ✅5 · Changed: rewritten
    # Then: new columns
    target = write(root, "data.csv", IRIS_HEADER)
    created.sync("p")
    target.write_text("a,b\n1,2\n3,4\n5,6\n")
    created.sync("p")
    assert stored_columns(created) == {"data.csv": ["a", "b"]}


def test_row_from_before_this_change_gets_columns_on_next_scan(root, created, monkeypatch):
    # ✅6 · Changed: `columns` NULL
    # Then: read once
    write(root, "data.csv", IRIS_HEADER)
    monkeypatch.setattr(created_module, "read_columns", lambda folder, path: None)  # a scan from before PCD-4
    created.sync("p")
    assert stored_columns(created) == {"data.csv": None}
    monkeypatch.undo()
    asked = opened_paths(monkeypatch)
    assert created.sync("p") is True  # the backfill counts as a change, so the panel refreshes
    assert stored_columns(created) == {"data.csv": IRIS_COLUMNS}
    created.sync("p")
    assert asked == ["data.csv"]


def test_parquet_schema_columns_are_read(root, created):
    # ✅7 · Changed: `.parquet` with five columns
    # Then: five names; no rows read
    # Demonstrates: A6
    table = pa.table({name: [1.0, 2.0] for name in IRIS_COLUMNS})
    pq.write_table(table, files_dir(root) / "data.parquet")
    created.sync("p")
    assert stored_columns(created) == {"data.parquet": IRIS_COLUMNS}


def test_xlsx_first_row_is_read(root, created):
    # ✅8 · Changed: `.xlsx`, header in row 1 of the first sheet
    # Then: five names
    # Demonstrates: A6
    workbook = openpyxl.Workbook()
    workbook.active.append(IRIS_COLUMNS)
    workbook.active.append([5.1, 3.5, 1.4, 0.2, "setosa"])
    workbook.save(files_dir(root) / "data.xlsx")
    created.sync("p")
    assert stored_columns(created) == {"data.xlsx": IRIS_COLUMNS}


def test_old_xls_gets_unknown_columns(root, created):
    # ❌1 · Changed: `.xls`
    # Then: `[]`
    # Demonstrates: A10
    write_bytes(root, "old.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 512)
    created.sync("p")
    assert stored_columns(created) == {"old.xls": []}


def test_empty_file_gets_unknown_columns(root, created):
    # ❌2 · Changed: 0 bytes
    # Then: `[]`
    write(root, "empty.csv", "")
    write(root, "empty.jsonl", "")
    created.sync("p")
    assert stored_columns(created) == {"empty.csv": [], "empty.jsonl": []}


def test_header_longer_than_64kb_gets_unknown_columns(root, created):
    # ❌3 · Changed: no newline in 64 KB
    # Then: `[]`
    # Demonstrates: S7
    write(root, "wide.csv", "x," * 40_000 + "\n1\n")
    created.sync("p")
    assert stored_columns(created) == {"wide.csv": []}


def test_columns_capped_at_50_names_of_60_chars(root, created):
    # ❌4 · Changed: 80 columns
    # Then: 50, cut
    # Demonstrates: S3
    names = ["n" * 200] + [f"c{i}" for i in range(79)]
    write(root, "many.csv", ",".join(names) + "\n")
    created.sync("p")
    [columns] = stored_columns(created).values()
    assert len(columns) == 50
    assert len(columns[0]) == 60 and columns[0].endswith("…")
    assert columns[1:] == [f"c{i}" for i in range(49)]


def test_unchanged_file_is_not_read_again(root, created, monkeypatch):
    # ❌5 · Changed: unchanged
    # Then: not opened
    # Demonstrates: S7
    write(root, "data.csv", IRIS_HEADER)
    asked = opened_paths(monkeypatch)
    created.sync("p")
    created.sync("p")
    created.sync("p")
    assert asked == ["data.csv"]


def test_renamed_file_keeps_its_columns_without_reading(root, created, monkeypatch):
    # ❌6 · Changed: rename
    # Then: kept, not opened
    target = write(root, "data.csv", IRIS_HEADER)
    created.sync("p")
    asked = opened_paths(monkeypatch)
    target.rename(files_dir(root) / "iris.csv")
    created.sync("p")
    assert stored_columns(created) == {"iris.csv": IRIS_COLUMNS}
    assert asked == []


# ---- PCD-4 Group S2 — Reading columns never leaves `files/`  (S6, S7) · unit (real tmp folder)
# Plan: docs/plans/PCD-4-reuse-existing-dataset-plan.md §7


def test_linked_file_is_not_read(root, tmp_path):
    # ❌1 · Changed: symlink to outside
    # Then: `[]`; target never opened
    secret = tmp_path / "secret.csv"
    secret.write_text("password,token\n")
    (files_dir(root)).mkdir(parents=True, exist_ok=True)
    (files_dir(root) / "data.csv").symlink_to(secret)
    before = secret.stat().st_atime_ns
    assert read_columns(files_dir(root), "data.csv") == []
    assert secret.stat().st_atime_ns == before


def test_file_in_linked_folder_is_not_read(root, tmp_path):
    # ❌2 · Changed: linked folder
    # Then: `[]`
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "data.csv").write_text("password,token\n")
    files_dir(root).mkdir(parents=True, exist_ok=True)
    (files_dir(root) / "sub").symlink_to(outside, target_is_directory=True)
    assert read_columns(files_dir(root), "sub/data.csv") == []
    assert read_columns(files_dir(root), "../outside/data.csv") == []


def test_gz_bomb_reads_at_most_64kb(root):
    # ❌3 · Changed: 1 GB expansion
    # Then: `[]`, ≤ 64 KB
    target = files_dir(root) / "bomb.csv.gz"
    target.parent.mkdir(parents=True, exist_ok=True)
    chunk = b"a" * (1 << 20)
    with gzip.open(target, "wb", compresslevel=1) as out:
        for _ in range(1024):
            out.write(chunk)
    started = time.monotonic()
    assert read_columns(files_dir(root), "bomb.csv.gz") == []
    assert time.monotonic() - started < 1


def test_broken_parquet_or_xlsx_gets_unknown_columns(root, created):
    # ❌4 · Changed: a `.parquet` / `.xlsx` with random bytes
    # Then: `[]`; scan goes on
    # Demonstrates: a bad file never breaks the scan
    write_bytes(root, "bad.parquet", os.urandom(4096))
    write_bytes(root, "bad.xlsx", b"PK\x03\x04" + os.urandom(4096))
    write(root, "good.csv", IRIS_HEADER)
    created.sync("p")
    assert stored_columns(created) == {"bad.parquet": [], "bad.xlsx": [], "good.csv": IRIS_COLUMNS}


def test_xlsx_reads_only_the_first_row(root, monkeypatch):
    # ❌5 · Changed: 100,000-row sheet
    # Then: only row 1 read (spy), fast
    # Demonstrates: S7
    workbook = openpyxl.Workbook(write_only=True)
    sheet = workbook.create_sheet()
    sheet.append(IRIS_COLUMNS)
    for i in range(100_000):
        sheet.append([i, i, i, i, "setosa"])
    files_dir(root).mkdir(parents=True, exist_ok=True)
    workbook.save(files_dir(root) / "big.xlsx")
    rows_read = []
    real = ReadOnlyWorksheet._cells_by_row

    def counting(self, *args, **kwargs):
        for row in real(self, *args, **kwargs):
            rows_read.append(1)
            yield row

    monkeypatch.setattr(ReadOnlyWorksheet, "_cells_by_row", counting)
    started = time.monotonic()
    assert read_columns(files_dir(root), "big.xlsx") == IRIS_COLUMNS
    assert len(rows_read) == 1
    assert time.monotonic() - started < 2
