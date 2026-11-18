"""Tests for per-project dataset views: which pool files a project may read, and
keeping its view folder equal to that set.

Pure function tests need no disk; sync tests use a real tmp folder (hard links)
and no Docker.
"""

import errno
import os

import pytest

from researchchat.workspace import ErrorCode, WorkspaceError
from researchchat.workspace.datasets.pool import (
    POOL_DIR,
    DatasetPool,
    PoolEntry,
    PoolFile,
)
from researchchat.workspace.datasets.store import ProjectDataset
from researchchat.workspace.datasets.views import (
    VIEW_FAILED_MESSAGE,
    VIEWS_DIR,
    ProjectViews,
    ViewFile,
    visible_pool_files,
)

# ---- The visible set is the tab's linked files · unit
# Baseline: project A has one ready download row `iris` → entry `iris@abc1234`,
# every file selected and ready; visible_pool_files runs.


IRIS = "iris@abc1234"


def pool_entry(entry_id=IRIS, ready=("a.csv", "b.csv"), not_ready=()):
    files = [PoolFile(p, 1, None, ready=True) for p in ready] + [PoolFile(p, 1, None) for p in not_ready]
    return PoolEntry(id=entry_id, source="huggingface", source_id="org/iris", revision="abc1234",
                     name="Iris", url=None, license=None, files=files)


def download_row(dataset_id="iris", entry_id=IRIS, files=("a.csv", "b.csv"), status="ready"):
    return ProjectDataset(id=dataset_id, pool_entry=entry_id, selection=None, status=status, files=list(files))


def test_visible_files_are_the_ready_selected_files_of_own_rows():
    # Then: both files of iris@abc1234 are in the set
    # Demonstrates: a project sees what its tab lists
    visible = visible_pool_files([download_row()], {IRIS: pool_entry()})
    assert visible == {ViewFile(IRIS, "a.csv"), ViewFile(IRIS, "b.csv")}


def test_same_entry_under_two_dataset_ids_appears_once():
    # Changed: a second row uses the same entry
    # Then: each file is in the set once
    # Demonstrates: sharing inside a project doesn't duplicate
    rows = [download_row(), download_row(dataset_id="iris-2")]
    assert visible_pool_files(rows, {IRIS: pool_entry()}) == {ViewFile(IRIS, "a.csv"), ViewFile(IRIS, "b.csv")}


def test_downloading_row_shows_only_finished_files():
    # Changed: the row is downloading and only one file is ready
    # Then: only the ready file is in the set
    # Demonstrates: partly downloaded data is readable as it lands
    entry = pool_entry(ready=("a.csv",), not_ready=("b.csv",))
    assert visible_pool_files([download_row(status="downloading")], {IRIS: entry}) == {ViewFile(IRIS, "a.csv")}


def test_entry_used_only_by_another_project_is_not_visible():
    # Changed: the entry is listed by project B only
    # Then: A's set is empty
    # Demonstrates: another project's data is never in A's set
    other = pool_entry("zenodo-123")
    a_rows = [download_row()]
    assert ViewFile("zenodo-123", "a.csv") not in visible_pool_files(a_rows, {IRIS: pool_entry(), "zenodo-123": other})
    assert visible_pool_files([], {"zenodo-123": other}) == set()


def test_unselected_pool_files_are_not_visible():
    # Changed: the row lists only a.csv
    # Then: only a.csv is in the set
    # Demonstrates: a file the tab doesn't list stays hidden
    assert visible_pool_files([download_row(files=("a.csv",))], {IRIS: pool_entry()}) == {ViewFile(IRIS, "a.csv")}


def test_not_ready_pool_file_is_not_visible():
    # Changed: one pool file is not ready
    # Then: that file is not in the set
    # Demonstrates: a half-written file is never exposed
    entry = pool_entry(ready=("a.csv",), not_ready=("b.csv",))
    assert ViewFile(IRIS, "b.csv") not in visible_pool_files([download_row()], {IRIS: entry})


def test_created_rows_add_no_pool_files():
    # Changed: the project only has a created dataset
    # Then: the set is empty
    # Demonstrates: created files stay in the project's own files folder
    # Created files are never ProjectDataset rows, so a project with only those passes no rows.
    assert visible_pool_files([], {IRIS: pool_entry()}) == set()


def test_failed_row_with_no_ready_files_adds_nothing():
    # Changed: the row failed and has no ready files
    # Then: the set is empty
    # Demonstrates: a failure leaves no partial access
    entry = pool_entry(ready=(), not_ready=("a.csv", "b.csv"))
    assert visible_pool_files([download_row(status="failed")], {IRIS: entry}) == set()


# ---- Syncing the view folder · unit, real tmp folder
# Baseline: an empty view for A and pool files on disk; ProjectViews.sync(A, visible) runs.


@pytest.fixture
def pool_root(tmp_path):
    root = tmp_path / "ws"
    for entry_id in (IRIS, "zenodo-123"):
        for name in ("a.csv", "b.csv"):
            path = root / POOL_DIR / entry_id / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"{entry_id}/{name}".encode())
    return root


def make_views(root):
    return ProjectViews(DatasetPool(root), root)


def pool_path(root, entry_id, name):
    return root / POOL_DIR / entry_id / name


def iris_files(*names):
    return {ViewFile(IRIS, name) for name in (names or ("a.csv", "b.csv"))}


def tree(folder):
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*"))


def snapshot(folder):
    return {p.relative_to(folder).as_posix(): (p.lstat().st_ino, p.lstat().st_mtime_ns) for p in folder.rglob("*")}


def test_sync_adds_hard_links_to_pool_files(pool_root):
    # Then: the view file exists and is the same file as the pool file; the bytes are stored once
    # Demonstrates: bytes are shared, not copied
    view = make_views(pool_root).sync("pa", iris_files())
    assert view == pool_root / VIEWS_DIR / "pa"
    assert tree(view) == [IRIS, f"{IRIS}/a.csv", f"{IRIS}/b.csv"]
    for name in ("a.csv", "b.csv"):
        assert os.path.samefile(view / IRIS / name, pool_path(pool_root, IRIS, name))
        assert pool_path(pool_root, IRIS, name).stat().st_nlink == 2


def test_sync_adds_a_file_while_others_stay_untouched(pool_root):
    # Changed: the view already has one file and a second becomes visible
    # Then: the new link is added and the old one keeps its inode
    # Demonstrates: a finishing download doesn't disturb data in use
    views = make_views(pool_root)
    view = views.sync("pa", iris_files("a.csv"))
    before = snapshot(view)[f"{IRIS}/a.csv"]
    views.sync("pa", iris_files())
    assert snapshot(view)[f"{IRIS}/a.csv"] == before
    assert os.path.samefile(view / IRIS / "b.csv", pool_path(pool_root, IRIS, "b.csv"))


def test_sync_relinks_a_file_whose_pool_inode_changed(pool_root):
    # Changed: the pool file was replaced by a fresh download
    # Then: the view link is the same file as the new pool file
    # Demonstrates: a re-downloaded file is read fresh
    views = make_views(pool_root)
    view = views.sync("pa", iris_files())
    fresh = pool_root / "fresh"
    fresh.write_bytes(b"new bytes")
    os.replace(fresh, pool_path(pool_root, IRIS, "a.csv"))
    views.sync("pa", iris_files())
    assert (view / IRIS / "a.csv").read_bytes() == b"new bytes"
    assert os.path.samefile(view / IRIS / "a.csv", pool_path(pool_root, IRIS, "a.csv"))


def test_sync_is_a_no_op_when_view_matches(pool_root):
    # Changed: the view is already correct
    # Then: nothing in the view is written (mtimes unchanged)
    # Demonstrates: it's safe to call on every change
    views = make_views(pool_root)
    view = views.sync("pa", iris_files())
    before = snapshot(view)
    views.sync("pa", iris_files())
    assert snapshot(view) == before


def test_sync_fails_when_pool_and_view_are_on_different_filesystems(pool_root, monkeypatch):
    # Changed: making the hard link fails with EXDEV
    # Then: WorkspaceError DOWNLOAD_FAILED with the readable-in-this-project message; the view is unchanged
    # Demonstrates: the bytes are never silently copied and the pool is never exposed
    def cross_device(source, target):
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(os, "link", cross_device)
    with pytest.raises(WorkspaceError) as raised:
        make_views(pool_root).sync("pa", iris_files())
    assert raised.value.code == ErrorCode.DOWNLOAD_FAILED and VIEW_FAILED_MESSAGE in str(raised.value)
    assert tree(pool_root / VIEWS_DIR / "pa") == []


def test_sync_never_writes_into_the_pool(pool_root):
    # Then: the pool folder's listing and mtimes are unchanged after sync
    # Demonstrates: the shared store is only read
    before = {k: v[1] for k, v in snapshot(pool_root / POOL_DIR).items()}
    views = make_views(pool_root)
    views.sync("pa", iris_files())
    views.sync("pa", set())
    assert {k: v[1] for k, v in snapshot(pool_root / POOL_DIR).items()} == before


# ---- Removing access · unit
# Baseline: A's and B's views both hold iris; A's row is removed and A is synced.


@pytest.fixture
def shared_views(pool_root):
    views = make_views(pool_root)
    views.sync("pa", iris_files())
    views.sync("pb", iris_files())
    return views


def test_sync_removes_files_no_longer_visible(shared_views, pool_root):
    # Then: A's view has no iris files and the empty entry folder is gone
    # Demonstrates: deleting from the tab revokes reading
    view = shared_views.sync("pa", set())
    assert tree(view) == []


def test_removing_from_one_project_keeps_other_project_view(shared_views, pool_root):
    # Then: B's view and the pool file are intact
    # Demonstrates: one project's delete never affects another
    shared_views.sync("pa", set())
    b_view = pool_root / VIEWS_DIR / "pb"
    assert tree(b_view) == [IRIS, f"{IRIS}/a.csv", f"{IRIS}/b.csv"]
    assert pool_path(pool_root, IRIS, "a.csv").read_bytes() == f"{IRIS}/a.csv".encode()


def test_cancelled_download_leaves_no_view_files(pool_root):
    # Changed: the row was cancelled mid-download
    # Then: A's view is empty
    # Demonstrates: cancelling revokes partial access too
    views = make_views(pool_root)
    views.sync("pa", iris_files("a.csv"))  # one file had landed before the cancel
    assert tree(views.sync("pa", set())) == []


# ---- Sync trusts nothing it finds · unit


def test_symlink_planted_in_view_is_removed_not_followed(pool_root):
    # Changed: the view contains a symlink nobody asked for
    # Then: the symlink is removed and its target is untouched
    # Demonstrates: a planted link can't widen access
    views = make_views(pool_root)
    view = views.sync("pa", iris_files())
    secret = pool_path(pool_root, "zenodo-123", "a.csv")
    (view / "zenodo-123").symlink_to(secret.parent)
    (view / IRIS / "planted.csv").symlink_to(secret)
    views.sync("pa", iris_files())
    assert tree(view) == [IRIS, f"{IRIS}/a.csv", f"{IRIS}/b.csv"]
    assert secret.read_bytes() == b"zenodo-123/a.csv"


def test_unknown_file_in_view_is_removed(pool_root):
    # Changed: the view contains an extra regular file
    # Then: it is removed
    # Demonstrates: the view only ever holds what the database allows
    views = make_views(pool_root)
    view = views.sync("pa", iris_files())
    (view / IRIS / "extra.csv").write_bytes(b"x")
    (view / "stray").mkdir()
    (view / "stray" / "y").write_bytes(b"y")
    views.sync("pa", iris_files())
    assert tree(view) == [IRIS, f"{IRIS}/a.csv", f"{IRIS}/b.csv"]


def test_unsafe_entry_id_is_never_linked(pool_root):
    # Changed: a visible file names the entry `../x`
    # Then: it is skipped and nothing is written outside the view
    # Demonstrates: a tampered row can't point the view outside the pool
    before = sorted(p.as_posix() for p in pool_root.rglob("*"))
    view = make_views(pool_root).sync("pa", {ViewFile("../x", "a.csv")})
    assert tree(view) == []
    after = sorted(p.as_posix() for p in pool_root.rglob("*"))
    assert [p for p in after if p not in before] == [str(pool_root / VIEWS_DIR), str(view)]
