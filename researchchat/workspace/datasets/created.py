"""Data files the project's own notebook code wrote, shown as datasets (PCD-1).

After every cell run the project's files/ folder is scanned (A2): data files
(CREATED_DATA_EXTENSIONS) get a card, a re-save updates it (AC4), a rename
keeps it (AC12), and a file that's gone shows `missing` (AC7). The scan never
follows a symlink and skips hidden entries and the top-level datasets/ folder,
where the pool links live (A5, AC10, SEC1, SEC8). Delete removes the file
itself, never a link target (A7, SEC1, SEC2).

Storage goes through created_store.py. Nothing here imports actions.py
or reads the Chainlit session; the run lock and the clock are injected (CLAUDE.md §2, DIP).

Plan: docs/plans/PCD-1-created-datasets-plan.md
"""

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING

from researchchat.clock import utc_now
from researchchat.config import CREATED_DATA_EXTENSIONS, WORKSPACES_DIR
from researchchat.workspace import ErrorCode, WorkspaceError, store
from researchchat.workspace.datasets import created_store as cds
from researchchat.workspace.datasets import store as ds
from researchchat.workspace.datasets.created_store import CreatedDataset, FileSnapshot
from researchchat.workspace.service import DatasetPanelStatus, DatasetProps

if TYPE_CHECKING:
    from researchchat.workspace.datasets.service import DatasetRecordView

RunLockFor = Callable[[str], asyncio.Lock]  # project_id -> its notebook run lock (SEC2)
Clock = Callable[[], str]  # ISO 8601 UTC now

POOL_LINKS_DIR = "datasets"  # files/datasets/: pool links, listed as downloaded datasets only (AC10)
NOTICE_NAME_MAX_CHARS = 80  # per file name in the toast (SEC6)
CREATED_SOURCE = "created"  # DatasetProps.source; the panel shows "Created by myself" (AC3)
ELLIPSIS = "…"


@dataclass
class ScanChanges:
    """What one scan found compared with the stored rows; computed without touching storage."""

    new_files: list[FileSnapshot] = field(default_factory=list)  # insert (AC1, AC13)
    resaved: list[CreatedDataset] = field(default_factory=list)  # same id, new size/mtime (AC4)
    renamed: list[CreatedDataset] = field(default_factory=list)  # same id, new path (AC12)

    @property
    def has_changes(self) -> bool:
        """False when the scan wrote nothing, so datasets_rev stays put (G2❌1, G3✅3)."""
        return bool(self.new_files or self.resaved or self.renamed)


# ---- the folder scan -----------------------------------------------------------


def is_data_file(name: str, extensions: tuple[str, ...] = CREATED_DATA_EXTENSIONS) -> bool:
    """True for Iris.csv, IRIS.CSV, a.csv.gz; False for plot.png, model.pkl, data (AC5, A4)."""
    lowered_name = name.lower()
    return any(lowered_name.endswith(extension) for extension in extensions)


def scan_data_files(files_dir: Path, extensions: tuple[str, ...] = CREATED_DATA_EXTENSIONS) -> list[FileSnapshot]:
    """Every data file under files/, by stat only (never reads contents, A9), in path order."""
    found: list[FileSnapshot] = []
    folders_to_visit: list[tuple[Path, str]] = [(files_dir, "")]
    while folders_to_visit:
        folder, relative_folder = folders_to_visit.pop()
        for entry in _listable_entries(folder, is_top_level=not relative_folder):
            relative_path = relative_folder + entry.name
            if entry.is_dir(follow_symlinks=False):
                folders_to_visit.append((Path(entry.path), relative_path + "/"))
            elif entry.is_file(follow_symlinks=False) and is_data_file(entry.name, extensions):
                found.append(_snapshot_of(entry, relative_path))
    return sorted(found, key=lambda snapshot: snapshot.path)


def _listable_entries(folder: Path, is_top_level: bool) -> list[os.DirEntry]:
    """Entries the scan may look at: no symlinks (SEC1), no hidden names (A5), not the pool links (SEC8)."""
    try:
        with os.scandir(folder) as entries:
            return [
                entry for entry in entries
                if not entry.is_symlink()
                and not entry.name.startswith(".")
                and not (is_top_level and entry.name == POOL_LINKS_DIR)
                and _is_storable_path(entry.name)
            ]
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return []  # removed or locked while scanning: picked up by the next run


def _snapshot_of(entry: os.DirEntry, relative_path: str) -> FileSnapshot:
    stat = entry.stat(follow_symlinks=False)
    return FileSnapshot(path=relative_path, size_bytes=stat.st_size, mtime_ns=stat.st_mtime_ns, inode=stat.st_ino)


def _is_storable_path(name: str) -> bool:
    """A name the database can hold and safe_relpath accepts (no backslash, not over PATH_MAX)."""
    try:
        return ds.safe_relpath(name) == name
    except WorkspaceError:
        return False


# ---- comparing a scan with the stored rows --------------------------------------


def compare_with_stored(stored: list[CreatedDataset], found: list[FileSnapshot]) -> ScanChanges:
    """Sort what a scan found into new / re-saved / renamed (pure; no I/O)."""
    stored_by_path = {dataset.snapshot.path: dataset for dataset in stored}
    found_paths = {snapshot.path for snapshot in found}
    # A rename keeps the inode, size and mtime; requiring all three stops a reused inode taking over a card (SEC10)
    gone_by_identity = {
        _identity(dataset.snapshot): dataset for dataset in stored if dataset.snapshot.path not in found_paths
    }
    changes = ScanChanges()
    for snapshot in found:
        _classify(snapshot, stored_by_path, gone_by_identity, changes)
    return changes


def _classify(
    snapshot: FileSnapshot,
    stored_by_path: dict[str, CreatedDataset],
    gone_by_identity: dict[tuple[int, int, int], CreatedDataset],
    changes: ScanChanges,
) -> None:
    known = stored_by_path.get(snapshot.path)
    if known is not None:
        if known.snapshot != snapshot:
            changes.resaved.append(replace(known, snapshot=snapshot))
        return
    renamed_from = gone_by_identity.pop(_identity(snapshot), None)
    if renamed_from is not None:
        changes.renamed.append(replace(renamed_from, snapshot=snapshot))
        return
    changes.new_files.append(snapshot)


def _identity(snapshot: FileSnapshot) -> tuple[int, int, int]:
    return (snapshot.inode, snapshot.size_bytes, snapshot.mtime_ns)


# ---- one file on disk ------------------------------------------------------------


def is_file_present(files_dir: Path, path: str) -> bool:
    """`ready` test: files/<path> is a regular file inside files/, and no part of it is a link (AC7)."""
    target = _path_with_no_linked_folder(files_dir, path)
    return target is not None and not target.is_symlink() and target.is_file()


def remove_created_file(files_dir: Path, path: str) -> int:
    """Delete files/<path> itself; a link there is unlinked, never followed. Returns the bytes freed.

    Nothing is touched when a folder on the way is a link: the file behind it isn't this project's (SEC1).
    """
    target = _path_with_no_linked_folder(files_dir, path)
    if target is None:
        return 0
    if target.is_symlink():
        target.unlink()
        return 0
    if not target.is_file():
        return 0
    freed_bytes = target.stat().st_size
    target.unlink()
    return freed_bytes


def _path_with_no_linked_folder(files_dir: Path, path: str) -> Path | None:
    """files_dir/path, not resolved; None when the path is unsafe or a folder on the way is a symlink."""
    try:
        parts = ds.safe_relpath(path).split("/")
    except WorkspaceError:
        return None
    folder = files_dir
    for folder_name in parts[:-1]:
        folder = folder / folder_name
        if folder.is_symlink():
            return None
    return folder / parts[-1]


# ---- the AC11 toast text ---------------------------------------------------------


def missing_notice(names: list[str]) -> str:
    """The AC11 toast text for these missing files, one line, names capped (SEC6)."""
    shown_names = [_one_line_name(name) for name in names]
    if len(shown_names) == 1:
        return (f"{shown_names[0]} was deleted or renamed and can't be found. "
                "Its card in the Datasets tab shows missing until you delete it.")
    return (f"{len(shown_names)} created files were deleted or renamed and can't be found: {', '.join(shown_names)}. "
            "Their cards in the Datasets tab show missing until you delete them.")


def _one_line_name(name: str) -> str:
    printable_name = "".join(character for character in name if character.isprintable())
    if len(printable_name) <= NOTICE_NAME_MAX_CHARS:
        return printable_name
    return printable_name[: NOTICE_NAME_MAX_CHARS - 1] + ELLIPSIS


# ---- the service -----------------------------------------------------------------


class CreatedDatasets:
    """The only place that lists, syncs or deletes created datasets."""

    def __init__(
        self,
        root: Path = WORKSPACES_DIR,
        extensions: tuple[str, ...] = CREATED_DATA_EXTENSIONS,
        run_lock: RunLockFor | None = None,
        clock: Clock = utc_now,
    ):
        # Only stores dependencies: actions.py builds this at import time.
        self.root = root
        self.extensions = extensions
        self.run_lock = run_lock  # set by actions.py from NotebookService, like NotebookService.datasets
        self.clock = clock
        self._own_locks: dict[str, asyncio.Lock] = {}  # used only when no run lock was injected (tests)

    def sync(self, project_id: str) -> bool:
        """Scan files/ and store what changed; True when any row changed (bump datasets_rev)."""
        stored = cds.load_created_datasets(project_id, self.root)
        changes = compare_with_stored(stored, scan_data_files(self._files_dir(project_id), self.extensions))
        self._store_changes(project_id, stored, changes)
        return changes.has_changes

    def panel_rows(self, project_id: str) -> list[DatasetProps]:
        """Created cards for NotebookProps.datasets: origin 'created', source 'created', no licence/url/shared (AC3)."""
        return [self._panel_row(project_id, dataset) for dataset in cds.load_created_datasets(project_id, self.root)]

    def model_views(self, project_id: str) -> "list[DatasetRecordView]":
        """Created rows for dataset_list: path /work/<path>, missing_files when gone (AC7, AC9)."""
        return [self._model_view(project_id, dataset) for dataset in cds.load_created_datasets(project_id, self.root)]

    def owns(self, project_id: str, dataset_id: str) -> bool:
        """True when this id is one of the project's created datasets (routes ds_delete, SEC3)."""
        return self._find(project_id, dataset_id) is not None

    async def delete(self, project_id: str, dataset_id: str) -> int:
        """Remove the file and its card; a link is unlinked, never followed (AC8, A7). Returns the bytes freed."""
        # Under the run lock no cell can swap the file for a link between the check and the unlink (SEC2)
        async with self._lock_for(project_id):
            dataset = self._find(project_id, dataset_id)
            if dataset is None:
                raise WorkspaceError(ErrorCode.NOT_FOUND, "Unknown dataset.")
            freed_bytes = remove_created_file(self._files_dir(project_id), dataset.snapshot.path)
            cds.delete_created_dataset(project_id, dataset_id, self.root)
        return freed_bytes

    def missing_names(self, project_id: str) -> list[str]:
        """Paths of created files that can't be found, for the AC11 toast."""
        files_dir = self._files_dir(project_id)
        return [
            dataset.snapshot.path for dataset in cds.load_created_datasets(project_id, self.root)
            if not is_file_present(files_dir, dataset.snapshot.path)
        ]

    # ---- helpers ----

    def _files_dir(self, project_id: str) -> Path:
        return store.project_dir(project_id, self.root) / store.FILES_DIR

    def _find(self, project_id: str, dataset_id: str) -> CreatedDataset | None:
        if not isinstance(dataset_id, str):
            return None
        return next((d for d in cds.load_created_datasets(project_id, self.root) if d.id == dataset_id), None)

    def _lock_for(self, project_id: str) -> asyncio.Lock:
        if self.run_lock is not None:
            return self.run_lock(project_id)
        return self._own_locks.setdefault(project_id, asyncio.Lock())

    def _store_changes(self, project_id: str, stored: list[CreatedDataset], changes: ScanChanges) -> None:
        now = self.clock()
        taken_ids = {dataset.id for dataset in stored}
        for snapshot in changes.new_files:
            dataset_id = cds.make_created_id(snapshot.path, taken_ids)
            taken_ids.add(dataset_id)
            cds.insert_created_dataset(project_id, CreatedDataset(dataset_id, snapshot, now, now), self.root)
        for dataset in changes.resaved + changes.renamed:
            cds.update_created_dataset(project_id, replace(dataset, changed_at=now), self.root)

    def _status(self, project_id: str, dataset: CreatedDataset) -> DatasetPanelStatus:
        return "ready" if is_file_present(self._files_dir(project_id), dataset.snapshot.path) else "missing"

    def _panel_row(self, project_id: str, dataset: CreatedDataset) -> DatasetProps:
        snapshot = dataset.snapshot
        return {
            "id": dataset.id,
            "name": _display_name(snapshot.path),
            "source": CREATED_SOURCE,
            "status": self._status(project_id, dataset),
            "done_bytes": None,
            "position_in_queue": None,
            "license": None,
            "size_bytes": snapshot.size_bytes,
            "file_count": 1,
            "url": None,
            "path": cds.kernel_file_path(snapshot.path),
            "downloaded_at": dataset.changed_at,
            "requested_at": dataset.first_seen_at,
            "files": [{"path": _display_name(snapshot.path), "size": snapshot.size_bytes}],
            "error": None,
            "shared_with": 0,
            "origin": "created",
        }

    def _model_view(self, project_id: str, dataset: CreatedDataset) -> "DatasetRecordView":
        status = self._status(project_id, dataset)
        kernel_path = cds.kernel_file_path(dataset.snapshot.path)
        return {
            "dataset_id": dataset.id,
            "name": _display_name(dataset.snapshot.path),
            "status": status,
            "done_bytes": None,
            "position_in_queue": None,
            "size_bytes": dataset.snapshot.size_bytes,
            "license": None,
            "url": None,
            "path": kernel_path,
            "files": [kernel_path],
            "file_count": 1,
            "missing_files": [kernel_path] if status == "missing" else [],
            "downloaded_at": dataset.changed_at,
            "error": None,
            "shared_with": 0,
            "origin": "created",
        }


def _display_name(path: str) -> str:
    """The file's own name, capped like catalog names (NAME_MAX)."""
    return path.rsplit("/", 1)[-1][: ds.NAME_MAX]
