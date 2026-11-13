"""The shared dataset pool (NB-4 plan §3.3).

workspaces/
    .dataset-pool/<entry>/<path>   the bytes, stored once; mounted read-only in every kernel
    .dataset-pool.json             the pool index (not visible to kernels)
    .dataset-partial/job-<n>/      downloads in progress, app-wide
    <project>/files/datasets/<id>/ relative links → ../../../../.dataset-pool/<entry>/<path>

The links are relative so they point at the same bytes on the host and in the
kernel: on the host they climb to workspaces/, in the kernel (/work/datasets/…)
they climb to / where the pool is mounted read-only at /.dataset-pool. The app
never trusts a link it finds: it compares the link text with the one it would
write and reads sizes from the pool folder itself (SEC23).

This module owns the pool index, linking files into projects, "used by"
counts, cleanup, rebuilding a broken index and the one-time migration from
NB-3's per-project storage. It never downloads and holds no lock of its own:
DatasetService calls it only while holding `lock` (one app-wide lock, so
cleanup and linking can't race, SEC9).

Plan: docs/plans/done/NB-4-dataset-pool-plan.md
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

from researchchat.config import WORKSPACES_DIR
from researchchat.workspace import ErrorCode, WorkspaceError, store
from researchchat.workspace import datasets_store as ds
from researchchat.workspace.datasets_store import DatasetRecord, ProjectDataset, Source

log = logging.getLogger(__name__)

POOL_DIR = ".dataset-pool"
POOL_INDEX_FILE = ".dataset-pool.json"
POOL_INDEX_FORMAT = 1
POOL_PARTIAL_DIR = ".dataset-partial"
KERNEL_POOL_ROOT = "/" + POOL_DIR  # where kernels see the pool; the relative links land here
LINK_CLIMB_TO_WORKSPACES = 4  # files/datasets/<id>/ → <id>, datasets, files, <project>
REVISION_PREFIX_LENGTH = 7  # "<dataset-id>@<first 7 of revision>"
ENTRY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}(@[a-z0-9]{1,7})?$")
BAD_INDEX_SUFFIX = ".bad"
HASH_CHUNK_BYTES = 1 << 20
UNKNOWN_SOURCE_ID = ""
STOPPED_DURING_DOWNLOAD = "app stopped during download"  # rebuilt entries whose catalog key was lost with the index


@dataclass
class PoolFile:
    path: str  # relative to the pool entry folder; checked by safe_relpath
    size: int  # bytes, as the catalog declared it
    checksum: str | None  # "md5:…" / "sha256:…", or None when the catalog gives none
    ready: bool = False  # downloaded, verified and moved into the entry folder
    mtime_ns: int | None = None  # lets the app notice a file changed on disk (SEC16)


@dataclass
class PoolEntry:
    id: str  # "<dataset-id>@<first 7 of revision>" (Zenodo: the dataset id); pool folder name
    source: Source  # which catalog
    source_id: str  # stable key in that catalog
    revision: str | None  # HF commit hash; None for Zenodo
    name: str  # title for people
    url: str | None  # landing page
    license: str | None  # shown in the details
    files: list[PoolFile] = field(default_factory=list)
    created_at: str = ""  # ISO 8601 UTC; "downloaded …" in details

    def file(self, path: str) -> PoolFile | None:
        return next((f for f in self.files if f.path == path), None)

    def ready_paths(self) -> set[str]:
        return {f.path for f in self.files if f.ready}


@dataclass
class LinkResult:
    linked_paths: list[str]  # files now visible in the project
    missing_paths: list[str]  # files the pool lacks; a download job must fetch them


@dataclass
class MigrationReport:
    migrated_projects: list[str] = field(default_factory=list)
    skipped_projects: list[str] = field(default_factory=list)  # corrupt manifests, logged (A6)


def checksum_matches(path: Path, checksum: str | None) -> bool:
    """True when the file's md5/sha256 is the one declared; no checksum means size alone was checked."""
    if not checksum:
        return True
    algorithm, _, expected = checksum.partition(":")
    if algorithm not in ("md5", "sha256"):
        return False
    digest = hashlib.new(algorithm)
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected.lower()


class DatasetPool:
    """The pool index and lock. One instance per app; callers hold `lock` for every change."""

    def __init__(self, root: Path = WORKSPACES_DIR):
        self.root = Path(root)
        self.lock = asyncio.Lock()  # index, linking and cleanup share it (SEC9)
        self._entries: dict[str, PoolEntry] | None = None  # cache of the index

    # ---- paths ----

    def pool_dir(self) -> Path:
        """workspaces/.dataset-pool/"""
        return self.root / POOL_DIR

    def partial_dir(self) -> Path:
        """workspaces/.dataset-partial/ (app-wide)."""
        return self.root / POOL_PARTIAL_DIR

    def entry_dir(self, entry_id: str) -> Path:
        """.dataset-pool/<entry>/, refused when the id isn't a generated entry id."""
        check_entry_id(entry_id)
        return self.pool_dir() / entry_id

    def pool_file_path(self, entry_id: str, relpath: str) -> Path:
        """.dataset-pool/<entry>/<relpath>; must stay inside the entry folder after resolve()."""
        return ds.path_inside(self.entry_dir(entry_id), relpath)

    @staticmethod
    def make_entry_id(dataset_slug: str, revision: str | None) -> str:
        """<dataset-slug>@<first 7 of revision>, or the slug when there's no revision (AC30)."""
        if not revision:
            return dataset_slug
        revision_prefix = re.sub(r"[^a-z0-9]", "", revision.lower())[:REVISION_PREFIX_LENGTH]
        return f"{dataset_slug}@{revision_prefix}" if revision_prefix else dataset_slug

    @staticmethod
    def link_target(entry_id: str, relpath: str) -> str:
        """The relative link text for files/datasets/<id>/<relpath>: the only target the app writes."""
        check_entry_id(entry_id)
        safe = ds.safe_relpath(relpath)
        climb = LINK_CLIMB_TO_WORKSPACES + safe.count("/")
        return "../" * climb + f"{POOL_DIR}/{entry_id}/{safe}"

    # ---- index ----

    def index_path(self) -> Path:
        return self.root / POOL_INDEX_FILE

    def entries(self) -> dict[str, PoolEntry]:
        """The index, read once and cached."""
        if self._entries is None:
            self._entries = {e.id: e for e in self.load_index()}
        return self._entries

    def forget_cached_index(self) -> None:
        """Read the index from disk again on next use."""
        self._entries = None

    def load_index(self) -> list[PoolEntry]:
        """Read .dataset-pool.json; a corrupt file is kept as .bad and the index rebuilt (G11❌4)."""
        path = self.index_path()
        if not path.is_file():
            return self.rebuild_index() if self.pool_dir().is_dir() else []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("format") != POOL_INDEX_FORMAT:
                raise ValueError("unknown format")
            return [_entry_from_dict(d) for d in data.get("entries") or []]
        except (ValueError, KeyError, TypeError, AttributeError, WorkspaceError):
            os.replace(path, path.with_name(POOL_INDEX_FILE + BAD_INDEX_SUFFIX))
            log.warning("Dataset pool index was unreadable; rebuilt it (old copy kept as .bad)")
            entries = self.rebuild_index()
            self.save_index(entries)
            return entries

    def save_index(self, entries: list[PoolEntry] | None = None) -> None:
        """Write .dataset-pool.json atomically (temp file + os.replace)."""
        listed = list(self.entries().values()) if entries is None else entries
        data = {"format": POOL_INDEX_FORMAT, "entries": [asdict(e) for e in listed]}
        path = self.index_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(POOL_INDEX_FILE + ".tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)

    def rebuild_index(self) -> list[PoolEntry]:
        """Rebuild from the folders in .dataset-pool/ (nothing is deleted).

        The catalog metadata went with the index, so a rebuilt entry keeps its
        files and its projects' links but isn't matched by new requests; files
        have no checksum, so they're trusted by size from now on.
        """
        entries = []
        if not self.pool_dir().is_dir():
            return entries
        for folder in sorted(self.pool_dir().iterdir()):
            if folder.is_symlink() or not folder.is_dir() or not ENTRY_ID_RE.match(folder.name):
                continue
            entries.append(PoolEntry(
                id=folder.name, source="huggingface", source_id=UNKNOWN_SOURCE_ID, revision=None,
                name=folder.name, url=None, license=None, files=_files_on_disk(folder),
            ))
        return entries

    def find_entries(self, source: Source, source_id: str) -> list[PoolEntry]:
        """Every pooled version of this dataset, newest first."""
        found = [e for e in self.entries().values() if e.source == source and e.source_id == source_id]
        return sorted(found, key=lambda e: e.created_at, reverse=True)

    def get_entry(self, entry_id: str) -> PoolEntry | None:
        return self.entries().get(entry_id)

    def add_entry(self, entry: PoolEntry) -> PoolEntry:
        """Store a new version; an id taken by another dataset gets -2, -3… (slugs can clash)."""
        entries = self.entries()
        base, n = entry.id, 2
        while entry.id in entries:
            slug, _, revision = base.partition("@")
            entry.id = f"{slug[:76]}-{n}" + (f"@{revision}" if revision else "")
            n += 1
        entries[entry.id] = entry
        return entry

    # ---- files in an entry ----

    def is_file_unchanged(self, entry: PoolEntry, pool_file: PoolFile) -> bool:
        """The pooled file is still there with the size and mtime_ns the index recorded."""
        try:
            stat = self.pool_file_path(entry.id, pool_file.path).lstat()
        except (OSError, WorkspaceError):
            return False
        return stat.st_size == pool_file.size and stat.st_mtime_ns == pool_file.mtime_ns

    def recheck_file(self, entry: PoolEntry, pool_file: PoolFile) -> bool:
        """Re-verify a changed file; a bad one is marked not ready and must be downloaded again (SEC16)."""
        path = self.pool_file_path(entry.id, pool_file.path)
        is_good = path.is_file() and not path.is_symlink() and path.stat().st_size == pool_file.size
        is_good = is_good and checksum_matches(path, pool_file.checksum)
        if is_good:
            pool_file.mtime_ns = path.stat().st_mtime_ns
        else:
            pool_file.ready = False
            path.unlink(missing_ok=True)
        return is_good

    def ensure_ready_files_intact(self, entry: PoolEntry, paths: list[str]) -> None:
        """Before linking: re-check every ready file among `paths` whose size or mtime changed."""
        for path in paths:
            pool_file = entry.file(path)
            if pool_file is not None and pool_file.ready and not self.is_file_unchanged(entry, pool_file):
                self.recheck_file(entry, pool_file)

    def store_file(self, entry: PoolEntry, pool_file: PoolFile, downloaded: Path) -> None:
        """Move a verified download into the entry folder and mark it ready."""
        target = self.pool_file_path(entry.id, pool_file.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(downloaded, target)
        pool_file.ready = True
        pool_file.mtime_ns = target.stat().st_mtime_ns
        existing = entry.file(pool_file.path)
        if existing is None:
            entry.files.append(pool_file)
        elif existing is not pool_file:
            entry.files[entry.files.index(existing)] = pool_file

    # ---- linking ----

    def link_files(self, project_id: str, dataset_id: str, entry: PoolEntry, paths: list[str]) -> LinkResult:
        """Link the ready pooled files among `paths` into files/datasets/<id>/; report the rest."""
        linked, missing = [], []
        for path in paths:
            pool_file = entry.file(path)
            if pool_file is None or not pool_file.ready:
                missing.append(path)
                continue
            self._write_link(project_id, dataset_id, entry.id, path)
            linked.append(path)
        return LinkResult(linked, missing)

    def _write_link(self, project_id: str, dataset_id: str, entry_id: str, relpath: str) -> None:
        link = ds.link_path(project_id, dataset_id, relpath, self.root)
        target = self.link_target(entry_id, relpath)
        if link.is_symlink() and os.readlink(link) == target:
            return
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.is_symlink() or link.is_file():
            link.unlink()
        elif link.exists():
            shutil.rmtree(link)
        os.symlink(target, link)

    def is_linked(self, project_id: str, dataset_id: str, entry: PoolEntry, relpath: str) -> bool:
        """The project's link is the one the app wrote, and the pooled file behind it is intact."""
        pool_file = entry.file(relpath)
        if pool_file is None or not pool_file.ready:
            return False
        try:
            link = ds.link_path(project_id, dataset_id, relpath, self.root)
            is_ours = link.is_symlink() and os.readlink(link) == self.link_target(entry.id, relpath)
            size_on_disk = self.pool_file_path(entry.id, relpath).lstat().st_size
        except (OSError, WorkspaceError):
            return False
        return is_ours and size_on_disk == pool_file.size

    def unlink_dataset(self, project_id: str, dataset_id: str) -> None:
        """Remove files/datasets/<id>/ without following links; never touches pool files."""
        ds.remove_dataset_dir(project_id, dataset_id, self.root)

    # ---- users and cleanup ----

    def projects_using(self, entry_id: str) -> list[str]:
        """Project ids whose datasets.json points to this entry (read from disk, the source of truth)."""
        users = []
        for project in store.list_projects(self.root):
            datasets = ds.load_project_datasets(project.id, self.root)
            if any(d.pool_entry == entry_id for d in datasets):
                users.append(project.id)
        return users

    def remove_unused_entry(self, entry_id: str) -> int:
        """Delete the entry when no project uses it (re-checked now, under the caller's lock); freed bytes."""
        entry = self.get_entry(entry_id)
        if entry is None or self.projects_using(entry_id):
            return 0
        freed = sum(f.size for f in entry.files if f.ready)
        folder = self.entry_dir(entry_id)
        if folder.is_symlink():
            folder.unlink()
        elif folder.exists():
            shutil.rmtree(folder)
        del self.entries()[entry_id]
        self.save_index()
        return freed

    # ---- migration from NB-3 ----

    def migrate(self) -> MigrationReport:
        """Move NB-3 datasets into the pool once, before any job runs (AC29, D8). Safe to run again."""
        report = MigrationReport()
        for project in store.list_projects(self.root):
            found_format = ds.read_manifest_format(project.id, self.root)
            if found_format == ds.MANIFEST_FORMAT:
                try:
                    self.migrate_project(project.id)
                except (OSError, WorkspaceError):
                    log.exception("Migrating datasets of project %s failed; retried on the next start", project.id)
                    report.skipped_projects.append(project.id)
                    continue
                report.migrated_projects.append(project.id)
            elif found_format == 0:
                log.warning("Skipped migrating datasets of project %s: datasets.json is unreadable", project.id)
                report.skipped_projects.append(project.id)
        return report

    def migrate_project(self, project_id: str) -> None:
        """Move one project's ready files into the pool, replace them with links, write format 2."""
        ds.recover_partials(project_id, self.root)
        records = ds.load_records(project_id, self.root)
        migrated = [self._migrate_record(project_id, record) for record in records]
        self.save_index()
        ds.back_up_v1_manifest(project_id, self.root)
        ds.save_project_datasets(project_id, migrated, self.root)

    def _migrate_record(self, project_id: str, record: DatasetRecord) -> ProjectDataset:
        entry = self._entry_for_record(record)
        self.save_index()  # before any move, so a crash mid-way finds the entry again (G14❌2)
        for record_file in record.files:
            if not record_file.ready:
                continue
            try:
                self._migrate_file(project_id, record, entry, record_file)
            except WorkspaceError:
                log.warning("Left %s of %s/%s in place: unsafe path", record_file.path, project_id, record.id)
        linked = self.link_files(project_id, record.id, entry, [f.path for f in record.files if f.ready])
        was_stopped = record.status in ("queued", "downloading")
        return ProjectDataset(
            id=record.id, pool_entry=entry.id, selection=record.selection, status="failed" if was_stopped else record.status,
            files=[f.path for f in record.files], requested_at=record.requested_at,
            linked_at=record.downloaded_at if linked.linked_paths else None,
            error=STOPPED_DURING_DOWNLOAD if was_stopped else record.error,
        )

    def _entry_for_record(self, record: DatasetRecord) -> PoolEntry:
        for entry in self.find_entries(record.source, record.source_id):
            if entry.revision == record.revision:
                return entry
        entry_id = self.make_entry_id(ds.base_id(record.source, record.source_id), record.revision)
        known = PoolEntry(
            id=entry_id, source=record.source, source_id=record.source_id, revision=record.revision,
            name=record.name, url=record.url, license=record.license, created_at=record.downloaded_at or record.requested_at,
        )
        rebuilt = self.get_entry(entry_id)
        if rebuilt is not None and rebuilt.source_id == UNKNOWN_SOURCE_ID:
            return self._restore_metadata(rebuilt, known)
        return self.add_entry(known)

    @staticmethod
    def _restore_metadata(rebuilt: PoolEntry, known: PoolEntry) -> PoolEntry:
        """A rebuilt entry (index lost) gets its catalog metadata back from an NB-3 record."""
        rebuilt.source, rebuilt.source_id, rebuilt.revision = known.source, known.source_id, known.revision
        rebuilt.name, rebuilt.url, rebuilt.license, rebuilt.created_at = known.name, known.url, known.license, known.created_at
        return rebuilt

    def _migrate_file(self, project_id: str, record: DatasetRecord, entry: PoolEntry, record_file: ds.DatasetFile) -> None:
        """Pool already has it → drop the project copy; else move it in once size and checksum match."""
        source = ds.link_path(project_id, record.id, record_file.path, self.root)  # refuses linked folders
        target = self.pool_file_path(entry.id, record_file.path)
        pool_file = entry.file(record_file.path) or PoolFile(record_file.path, record_file.size, record_file.checksum)
        if entry.file(record_file.path) is None:
            entry.files.append(pool_file)
        is_regular_file = source.is_file() and not source.is_symlink()
        if pool_file.ready or self._adopt_moved_file(pool_file, target):
            if is_regular_file:
                source.unlink()
            return
        is_intact = is_regular_file and source.stat().st_size == record_file.size
        if not (is_intact and checksum_matches(source, record_file.checksum)):
            return  # gone or changed: left in place, not ready in the pool (G14❌1)
        self.move_into_pool(source, target)
        pool_file.ready, pool_file.mtime_ns = True, target.stat().st_mtime_ns

    @staticmethod
    def _adopt_moved_file(pool_file: PoolFile, target: Path) -> bool:
        """A crash after the move but before the index was saved: the file is already in the pool."""
        is_there = target.is_file() and not target.is_symlink() and target.stat().st_size == pool_file.size
        if is_there and checksum_matches(target, pool_file.checksum):
            pool_file.ready, pool_file.mtime_ns = True, target.stat().st_mtime_ns
            return True
        return False

    @staticmethod
    def move_into_pool(source_path: Path, target_path: Path) -> None:
        """os.rename on one disk; copy then delete when the pool is on another disk (A14)."""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.rename(source_path, target_path)
        except OSError:
            shutil.copy2(source_path, target_path)
            source_path.unlink()


def check_entry_id(entry_id: object) -> None:
    """Only generated entry ids name a pool folder (SEC23)."""
    if not isinstance(entry_id, str) or not ENTRY_ID_RE.match(entry_id):
        raise WorkspaceError(ErrorCode.NOT_FOUND, "Unknown dataset.")


def _entry_from_dict(d: dict) -> PoolEntry:
    entry = PoolEntry(
        id=str(d["id"]), source=d["source"], source_id=str(d["source_id"]), revision=d.get("revision"),
        name=str(d.get("name") or d["id"])[: ds.NAME_MAX], url=d.get("url"), license=d.get("license"),
        files=[
            PoolFile(ds.safe_relpath(f["path"]), int(f["size"]), f.get("checksum"), bool(f.get("ready", False)), f.get("mtime_ns"))
            for f in d.get("files") or []
        ],
        created_at=str(d.get("created_at") or ""),
    )
    check_entry_id(entry.id)
    if entry.source not in ("huggingface", "zenodo"):
        raise ValueError("bad source")
    return entry


def _files_on_disk(folder: Path) -> list[PoolFile]:
    files = []
    for path in sorted(folder.rglob("*")):
        if path.is_file() and not path.is_symlink():
            stat = path.stat()
            files.append(PoolFile(path.relative_to(folder).as_posix(), stat.st_size, None, True, stat.st_mtime_ns))
    return files
