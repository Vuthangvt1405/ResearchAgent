"""Data files the project's own notebook code wrote, shown as datasets.

After every cell run the project's files/ folder is scanned: data files
(CREATED_DATA_EXTENSIONS) get a card, a re-save updates it, a rename
keeps it, and a file that's gone shows `missing`. The scan never
follows a symlink and skips hidden entries and the top-level datasets/ folder,
where the pool links live. Delete removes the file
itself, never a link target.

Storage goes through created_store.py. Nothing here imports actions.py
or reads the Chainlit session; the run lock and the clock are injected (DIP).
"""

import asyncio
import csv
import gzip
import json
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO, Literal

from researchchat.clock import utc_now
from researchchat.config import CREATED_DATA_EXTENSIONS, WORKSPACES_DIR
from researchchat.workspace import ErrorCode, WorkspaceError, store
from researchchat.workspace.datasets import created_store as cds
from researchchat.workspace.datasets import store as ds
from researchchat.workspace.datasets.created_store import CreatedDataset, FileSnapshot
from researchchat.workspace.datasets.describe import describe_need
from researchchat.workspace.datasets.load_code import load_code
from researchchat.workspace.service import DatasetPanelStatus, DatasetProps

CreatedBy = Literal["assistant", "user", "upload"]  # a cell run by either, or put in by the user (no run)

if TYPE_CHECKING:
    from researchchat.workspace.datasets.service import DatasetRecordView

RunLockFor = Callable[[str], asyncio.Lock]  # project_id -> its notebook run lock
Clock = Callable[[], str]  # ISO 8601 UTC now

POOL_LINKS_DIR = "datasets"  # files/datasets/: pool links, listed as downloaded datasets only
NOTICE_NAME_MAX_CHARS = 80  # per file name in the toast
CREATED_SOURCE = "created"  # DatasetProps.source; the panel shows "Created by myself"
ELLIPSIS = "…"
COLUMNS_READ_MAX_BYTES = 64 * 1024  # text files: at most this much (after decompressing) is read for the header
COLUMNS_MAX = 50  # column names kept per file
COLUMN_NAME_MAX_CHARS = 60  # per column name


@dataclass
class ScanChanges:
    """What one scan found compared with the stored rows; computed without touching storage."""

    new_files: list[FileSnapshot] = field(default_factory=list)  # insert
    resaved: list[CreatedDataset] = field(default_factory=list)  # same id, new size/mtime
    renamed: list[CreatedDataset] = field(default_factory=list)  # same id, new path

    @property
    def has_changes(self) -> bool:
        """False when the scan wrote nothing, so datasets_rev stays put."""
        return bool(self.new_files or self.resaved or self.renamed)


# ---- the folder scan -----------------------------------------------------------


def is_data_file(name: str, extensions: tuple[str, ...] = CREATED_DATA_EXTENSIONS) -> bool:
    """True for Iris.csv, IRIS.CSV, a.csv.gz; False for plot.png, model.pkl, data."""
    lowered_name = name.lower()
    return any(lowered_name.endswith(extension) for extension in extensions)


def scan_data_files(files_dir: Path, extensions: tuple[str, ...] = CREATED_DATA_EXTENSIONS) -> list[FileSnapshot]:
    """Every data file under files/, by stat only (never reads contents), in path order."""
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
    """Entries the scan may look at: no symlinks, no hidden names, not the pool links."""
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
    # A rename keeps the inode, size and mtime; requiring all three stops a reused inode taking over a card
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
    """`ready` test: files/<path> is a regular file inside files/, and no part of it is a link."""
    target = _path_with_no_linked_folder(files_dir, path)
    return target is not None and not target.is_symlink() and target.is_file()


def remove_created_file(files_dir: Path, path: str) -> int:
    """Delete files/<path> itself; a link there is unlinked, never followed. Returns the bytes freed.

    Nothing is touched when a folder on the way is a link: the file behind it isn't this project's.
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


# ---- column names -----------------------------------------------------------------


def read_columns(files_dir: Path, path: str) -> list[str]:
    """Column names of files/<path>, or [] when none can be read; never raises.

    CSV / TSV (also .gz): the first line. JSON / JSONL: the keys of the first
    record. Parquet: the schema from the footer (pyarrow). .xlsx: the first row
    of the first sheet (openpyxl, read-only). .xls and anything else: [].
    """
    target = _path_with_no_linked_folder(files_dir, path)
    if target is None:
        return []
    try:
        fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return []  # a link (ELOOP), gone, or locked
    try:
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                return []
            names = _names_from(handle, path.lower())
    except Exception:  # noqa: BLE001 — a broken or hostile file must never break the scan
        return []
    return _clean_names(names)


def _names_from(handle: BinaryIO, lowered_path: str) -> list:
    """Raw column names from an open file, by its suffix."""
    if lowered_path.endswith((".csv", ".tsv", ".csv.gz", ".tsv.gz")):
        stream = gzip.GzipFile(fileobj=handle) if lowered_path.endswith(".gz") else handle
        line = _first_line(stream)
        delimiter = "\t" if ".tsv" in lowered_path else ","
        return next(csv.reader([line], delimiter=delimiter), []) if line else []
    if lowered_path.endswith(".jsonl"):
        line = _first_line(handle)
        record = json.loads(line) if line.strip() else None
        return list(record) if isinstance(record, dict) else []
    if lowered_path.endswith(".json"):
        return _json_first_record_keys(handle.read(COLUMNS_READ_MAX_BYTES).decode("utf-8", "replace"))
    if lowered_path.endswith(".parquet"):
        import pyarrow.parquet as pq  # only the footer is read

        return list(pq.read_schema(handle).names)
    if lowered_path.endswith(".xlsx"):
        return _xlsx_first_row(handle)
    return []


def _first_line(stream) -> str:
    """The first line within COLUMNS_READ_MAX_BYTES; "" when none ends there (one huge line) or the file is empty."""
    data = stream.read(COLUMNS_READ_MAX_BYTES + 1)
    end = data.find(b"\n")
    if end == -1:
        if len(data) > COLUMNS_READ_MAX_BYTES:
            return ""
        end = len(data)
    return data[:end].decode("utf-8", "replace").lstrip("\ufeff").rstrip("\r")


def _json_first_record_keys(text: str) -> list:
    """Keys of the first object in a JSON array of records, or of a top-level object; [] otherwise."""
    text = text.lstrip("\ufeff \t\r\n")
    decoder = json.JSONDecoder()
    if text.startswith("["):
        record, _ = decoder.raw_decode(text[1:].lstrip())
    else:
        record, _ = decoder.raw_decode(text)
    return list(record) if isinstance(record, dict) else []


def _xlsx_first_row(handle: BinaryIO) -> list:
    import openpyxl  # read-only mode streams rows; only row 1 is asked for

    workbook = openpyxl.load_workbook(handle, read_only=True, data_only=True)
    try:
        first_row = next(workbook.worksheets[0].iter_rows(min_row=1, max_row=1, values_only=True), ())
    finally:
        workbook.close()
    return [value for value in first_row if value is not None]


def _clean_names(names: list) -> list[str]:
    """One printable line per name, ≤ COLUMN_NAME_MAX_CHARS, empty ones dropped, at most COLUMNS_MAX."""
    cleaned = []
    for name in names:
        text = " ".join("".join(c if c.isprintable() else " " for c in str(name)).split())
        if len(text) > COLUMN_NAME_MAX_CHARS:
            text = text[: COLUMN_NAME_MAX_CHARS - 1] + ELLIPSIS
        if text:
            cleaned.append(text)
    return cleaned[:COLUMNS_MAX]


# ---- the missing-files toast text ---------------------------------------------------------


def missing_notice(names: list[str]) -> str:
    """The missing-files toast text, one line, names capped."""
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

    def sync(self, project_id: str, by: CreatedBy | None = None) -> bool:
        """Scan files/ and store what changed; True when any row changed (bump datasets_rev).

        `by` is whose run just ended; None (a scan with no run, e.g. a chat opening) means
        new files were put there by the user: uploads.
        """
        stored = cds.load_created_datasets(project_id, self.root)
        changes = compare_with_stored(stored, scan_data_files(self._files_dir(project_id), self.extensions))
        self._store_changes(project_id, stored, changes, by or "upload")
        filled = self._fill_missing_columns(project_id, stored, changes)
        return changes.has_changes or filled

    def panel_rows(self, project_id: str) -> list[DatasetProps]:
        """Created cards for NotebookProps.datasets: origin 'created', source 'created', no licence/url/shared."""
        return [self._panel_row(project_id, dataset) for dataset in cds.load_created_datasets(project_id, self.root)]

    def model_views(self, project_id: str) -> "list[DatasetRecordView]":
        """Created rows for dataset_list: path /work/<path>, missing_files when gone."""
        return [self._model_view(project_id, dataset) for dataset in cds.load_created_datasets(project_id, self.root)]

    def owns(self, project_id: str, dataset_id: str) -> bool:
        """True when this id is one of the project's created datasets (routes ds_delete)."""
        return self._find(project_id, dataset_id) is not None

    async def delete(self, project_id: str, dataset_id: str) -> int:
        """Remove the file and its card; a link is unlinked, never followed. Returns the bytes freed."""
        # Under the run lock no cell can swap the file for a link between the check and the unlink
        async with self._lock_for(project_id):
            dataset = self._find(project_id, dataset_id)
            if dataset is None:
                raise WorkspaceError(ErrorCode.NOT_FOUND, "Unknown dataset.")
            freed_bytes = remove_created_file(self._files_dir(project_id), dataset.snapshot.path)
            cds.delete_created_dataset(project_id, dataset_id, self.root)
        return freed_bytes

    def save_description(self, project_id: str, dataset_id: str, text: str) -> None:
        """Store the assistant's one-line description on one created row of this project."""
        dataset = self._find(project_id, dataset_id)
        if dataset is None:
            raise WorkspaceError(ErrorCode.NOT_FOUND, "Unknown dataset.")
        cds.update_created_dataset(project_id, replace(dataset, assistant_description=text), self.root)

    def missing_names(self, project_id: str) -> list[str]:
        """Paths of created files that can't be found, for the missing-files toast."""
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

    def _store_changes(self, project_id: str, stored: list[CreatedDataset], changes: ScanChanges, by: CreatedBy) -> None:
        """New files get their columns and who made them; a re-save re-reads the columns and drops the
        assistant's note (it described the old contents); a rename keeps both without reading the file."""
        now = self.clock()
        files_dir = self._files_dir(project_id)
        taken_ids = {dataset.id for dataset in stored}
        for snapshot in changes.new_files:
            dataset_id = cds.make_created_id(snapshot.path, taken_ids)
            taken_ids.add(dataset_id)
            dataset = CreatedDataset(
                dataset_id, snapshot, now, now, columns=read_columns(files_dir, snapshot.path), created_by=by,
            )
            cds.insert_created_dataset(project_id, dataset, self.root)
        for dataset in changes.resaved:
            columns = read_columns(files_dir, dataset.snapshot.path)
            resaved = replace(dataset, changed_at=now, columns=columns, assistant_description=None)
            cds.update_created_dataset(project_id, resaved, self.root)
        for dataset in changes.renamed:
            cds.update_created_dataset(project_id, replace(dataset, changed_at=now), self.root)

    def _fill_missing_columns(self, project_id: str, stored: list[CreatedDataset], changes: ScanChanges) -> bool:
        """Rows stored before column names existed (columns None) are read once; True when any was filled."""
        changed_ids = {dataset.id for dataset in changes.resaved + changes.renamed}
        files_dir = self._files_dir(project_id)
        filled = False
        for dataset in stored:
            if dataset.columns is None and dataset.id not in changed_ids and is_file_present(files_dir, dataset.snapshot.path):
                cds.update_created_dataset(
                    project_id, replace(dataset, columns=read_columns(files_dir, dataset.snapshot.path)), self.root,
                )
                filled = True
        return filled

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
            "assistant_description": dataset.assistant_description,
        }

    def _model_view(self, project_id: str, dataset: CreatedDataset) -> "DatasetRecordView":
        status = self._status(project_id, dataset)
        kernel_path = cds.kernel_file_path(dataset.snapshot.path)
        view: DatasetRecordView = {
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
            "description": None,
            "columns": dataset.columns,
            "assistant_description": dataset.assistant_description,
        }
        view["describe"] = describe_need(view, created_by=dataset.created_by)
        view["load_code"] = load_code(view)
        return view


def _display_name(path: str) -> str:
    """The file's own name, capped like catalog names (NAME_MAX)."""
    return path.rsplit("/", 1)[-1][: ds.NAME_MAX]
