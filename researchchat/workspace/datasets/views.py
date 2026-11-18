"""Per-project dataset views: what a project's kernel sees at /.dataset-pool.

workspaces/
    .dataset-views/<project>/<entry>/<path>   hard links to the pool files the project's tab lists

A kernel mounts its own project's view read-only at /.dataset-pool instead of
the whole pool, so the relative links in files/datasets/ land on that
project's files only and another project's data is simply not there. Hard
links share the pool's bytes (nothing is copied), and a link added on the
host shows up in a running container at once, so no restart is needed.

The view is always rebuilt from the database: `visible_pool_files` computes
what may be seen and `ProjectViews.sync` makes the folder match, trusting
nothing it finds there. Callers hold the pool lock, like every pool change.
"""

import logging
import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from researchchat.config import WORKSPACES_DIR
from researchchat.workspace import ErrorCode, WorkspaceError, store
from researchchat.workspace.datasets import store as ds
from researchchat.workspace.datasets.pool import DatasetPool, PoolEntry
from researchchat.workspace.datasets.store import ProjectDataset

log = logging.getLogger(__name__)

VIEWS_DIR = ".dataset-views"
VIEW_FAILED_MESSAGE = "Couldn't make the dataset readable in this project"


@dataclass(frozen=True)
class ViewFile:
    """One pool file a project may read."""

    entry_id: str  # pool folder name (checked by check_entry_id); also the folder name in the view
    path: str  # file inside the entry (checked by safe_relpath); the same path the project's link uses


def visible_pool_files(datasets: Iterable[ProjectDataset], entries: dict[str, PoolEntry]) -> set[ViewFile]:
    """The pool files a project may read: its download rows' files that are ready in the pool."""
    visible: set[ViewFile] = set()
    for dataset in datasets:
        entry = entries.get(dataset.pool_entry)
        if entry is None:
            continue
        ready_listed_paths = set(dataset.files) & entry.ready_paths()
        visible.update(ViewFile(entry.id, path) for path in ready_listed_paths)
    return visible


class ProjectViews:
    """Keeps each project's view folder equal to what its tab lists."""

    def __init__(self, pool: DatasetPool, root: Path = WORKSPACES_DIR):
        self.pool = pool  # where the real bytes are; the only place link sources come from
        self.root = Path(root)

    def views_dir(self) -> Path:
        """workspaces/.dataset-views/"""
        return self.root / VIEWS_DIR

    def view_dir(self, project_id: str) -> Path:
        """workspaces/.dataset-views/<project>/, the folder its kernel mounts at /.dataset-pool."""
        store.project_dir(project_id, self.root)  # NOT_FOUND for an id that isn't a safe project slug
        return self.views_dir() / project_id

    def sync(self, project_id: str, visible: set[ViewFile]) -> Path:
        """Make the project's view hold exactly `visible`; returns the view folder."""
        view = self.view_dir(project_id)
        _replace_links_with_folder(self.views_dir())
        _replace_links_with_folder(view)
        wanted = self._pool_sources(visible)
        _remove_unwanted(view, wanted)
        try:
            for relpath, source in wanted.items():
                _link_pool_file(source, view / relpath)
        finally:
            _remove_empty_folders(view)  # a failed link leaves no empty entry folder behind
        return view

    def prune(self, known_project_ids: set[str]) -> None:
        """Remove the views of projects that no longer exist, so leftovers don't keep bytes alive."""
        views = self.views_dir()
        if views.is_symlink() or not views.is_dir():
            return
        for child in views.iterdir():
            if child.name not in known_project_ids:
                ds.remove_tree(child)

    def _pool_sources(self, visible: set[ViewFile]) -> dict[str, Path]:
        """view-relative path -> the pool file it must be; a file naming an unsafe entry or path is skipped."""
        sources: dict[str, Path] = {}
        for view_file in visible:
            try:
                source = self.pool.pool_file_path(view_file.entry_id, view_file.path)
            except WorkspaceError:
                log.warning("Skipped an unsafe dataset view file: %r", view_file.entry_id[:80])
                continue
            sources[f"{view_file.entry_id}/{ds.safe_relpath(view_file.path)}"] = source
        return sources


def _replace_links_with_folder(folder: Path) -> None:
    """The folder must be a real directory; a link or file found in its place is removed, never followed."""
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        folder.unlink()
    folder.mkdir(parents=True, exist_ok=True)


def _is_same_file(link: Path, source: Path) -> bool:
    """A real file in the view that shares the pool file's inode (a re-downloaded pool file has a new one)."""
    try:
        return not link.is_symlink() and link.is_file() and os.path.samefile(link, source)
    except OSError:
        return False


def _remove_unwanted(view: Path, wanted: dict[str, Path]) -> None:
    """Delete everything in the view that isn't a wanted file; links aren't followed.

    A wanted file whose pool inode changed stays until `_link_pool_file` swaps it, so readers never see a gap."""
    for folder, folder_names, file_names in os.walk(view):
        base = Path(folder)
        for name in folder_names:
            if (base / name).is_symlink():
                (base / name).unlink()
        for name in file_names:
            path = base / name
            is_wanted = path.relative_to(view).as_posix() in wanted
            if not is_wanted or path.is_symlink():
                path.unlink()


def _link_pool_file(source: Path, target: Path) -> None:
    """Hard-link the pool file into the view through a temp name, so a running cell never sees half a link."""
    if _is_same_file(target, source):
        return
    temp = target.with_name(f".{target.name}.linking")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp.unlink(missing_ok=True)
        os.link(source, temp)
        os.replace(temp, target)
    except OSError as error:
        temp.unlink(missing_ok=True)
        # Never copy (doubles the disk) and never fall back to mounting the whole pool
        raise WorkspaceError(ErrorCode.DOWNLOAD_FAILED, VIEW_FAILED_MESSAGE) from error


def _remove_empty_folders(view: Path) -> None:
    for folder, _, _ in os.walk(view, topdown=False):
        path = Path(folder)
        if path != view and not any(path.iterdir()):
            path.rmdir()
