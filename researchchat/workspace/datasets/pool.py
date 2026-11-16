"""The shared dataset pool (NB-4 plan §3.3).

workspaces/
    .dataset-pool/<entry>/<path>   the bytes, stored once; mounted read-only in every kernel
    researchchat.db                the pool index: pool_entries + pool_files (not visible to kernels)
    .dataset-partial/job-<n>/      downloads in progress, app-wide
    <project>/files/datasets/<id>/ relative links → ../../../../.dataset-pool/<entry>/<path>

The links are relative so they point at the same bytes on the host and in the
kernel: on the host they climb to workspaces/, in the kernel (/work/datasets/…)
they climb to / where the pool is mounted read-only at /.dataset-pool. The app
never trusts a link it finds: it compares the link text with the one it would
write and reads sizes from the pool folder itself (SEC23).

This module owns the pool index, linking files into projects, "used by"
counts and cleanup. It never downloads and holds no lock of its own:
DatasetService calls it only while holding `lock` (one app-wide lock, so
cleanup and linking can't race, SEC9).

Plans: docs/plans/done/NB-4-dataset-pool-plan.md, docs/plans/sqlite-alembic-storage-plan.md
"""

import asyncio
import hashlib
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Connection, Row, delete, func, insert, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from researchchat.config import WORKSPACES_DIR
from researchchat.db.engine import database_for
from researchchat.db.schema import pool_entries, pool_files, project_datasets, projects
from researchchat.workspace import ErrorCode, WorkspaceError
from researchchat.workspace.datasets import store as ds
from researchchat.workspace.datasets.store import Source

log = logging.getLogger(__name__)

POOL_DIR = ".dataset-pool"
POOL_PARTIAL_DIR = ".dataset-partial"
KERNEL_POOL_ROOT = "/" + POOL_DIR  # where kernels see the pool; the relative links land here
LINK_CLIMB_TO_WORKSPACES = 4  # files/datasets/<id>/ → <id>, datasets, files, <project>
REVISION_PREFIX_LENGTH = 7  # "<dataset-id>@<first 7 of revision>"
ENTRY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}(@[a-z0-9]{1,7})?$")
HASH_CHUNK_BYTES = 1 << 20


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

    def entries(self) -> dict[str, PoolEntry]:
        """The index, read once and cached."""
        if self._entries is None:
            self._entries = {e.id: e for e in self.load_index()}
        return self._entries

    def load_index(self) -> list[PoolEntry]:
        """Read the pool index from the database; a tampered row is skipped and logged (SEC23)."""
        with database_for(self.root).connect() as connection:
            entry_rows = connection.execute(select(pool_entries).order_by(pool_entries.c.pk)).all()
            files_by_entry = _pool_files_by_entry(connection)
        entries = (_entry_from_row(row, files_by_entry.get(row.pk, [])) for row in entry_rows)
        return [entry for entry in entries if entry is not None]

    def save_index(self, entries: list[PoolEntry] | None = None) -> None:
        """Write the index in one transaction: upsert entries on slug (keeps their pk), replace their files,
        delete entries no longer listed (a used one is refused by the RESTRICT foreign key, SEC4)."""
        listed = list(self.entries().values()) if entries is None else entries
        with database_for(self.root).begin() as connection:
            for entry in listed:
                entry_pk = _upsert_entry(connection, entry)
                _replace_entry_files(connection, entry_pk, entry.files)
            listed_slugs = [entry.id for entry in listed]
            connection.execute(delete(pool_entries).where(pool_entries.c.slug.not_in(listed_slugs)))

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

    def link_files(self, project_id: str, dataset_id: str, entry: PoolEntry, paths: list[str]) -> None:
        """Link the ready pooled files among `paths` into files/datasets/<id>/; the rest wait for a download job."""
        for path in paths:
            pool_file = entry.file(path)
            if pool_file is not None and pool_file.ready:
                self._write_link(project_id, dataset_id, entry.id, path)

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
        """Project ids whose datasets point to this entry, in project-bar order (one query)."""
        query = (
            select(projects.c.slug)
            .join(project_datasets, project_datasets.c.project_pk == projects.c.pk)
            .join(pool_entries, pool_entries.c.pk == project_datasets.c.pool_entry_pk)
            .where(pool_entries.c.slug == entry_id)
            .distinct()
            .order_by(func.lower(projects.c.name), projects.c.slug)
        )
        with database_for(self.root).connect() as connection:
            return list(connection.scalars(query))

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

def check_entry_id(entry_id: object) -> None:
    """Only generated entry ids name a pool folder (SEC23)."""
    if not isinstance(entry_id, str) or not ENTRY_ID_RE.match(entry_id):
        raise WorkspaceError(ErrorCode.NOT_FOUND, "Unknown dataset.")


def _pool_files_by_entry(connection: Connection) -> dict[int, list[Row]]:
    files: dict[int, list[Row]] = {}
    for row in connection.execute(select(pool_files).order_by(pool_files.c.entry_pk, pool_files.c.position)):
        files.setdefault(row.entry_pk, []).append(row)
    return files


def _entry_from_row(row: Row, file_rows: list[Row]) -> PoolEntry | None:
    """A PoolEntry, or None (logged) when its id, source or a file path was edited into something unsafe."""
    try:
        check_entry_id(row.slug)
        files = [
            PoolFile(ds.safe_relpath(f.path), f.size, f.checksum, f.ready, f.mtime_ns) for f in file_rows
        ]
    except WorkspaceError:
        log.warning("Ignored a pool entry row with an unsafe id or file path: %r", row.slug[:80])
        return None
    if row.source not in ("huggingface", "zenodo"):
        log.warning("Ignored a pool entry row with an unknown source: %r", row.slug[:80])
        return None
    return PoolEntry(
        id=row.slug, source=row.source, source_id=row.source_id, revision=row.revision,
        name=row.name[: ds.NAME_MAX], url=row.url, license=row.license, files=files, created_at=row.created_at,
    )


def _upsert_entry(connection: Connection, entry: PoolEntry) -> int:
    """Insert or update one entry by slug; the pk stays the same, so project rows keep pointing at it."""
    values = {
        "source": entry.source, "source_id": entry.source_id, "revision": entry.revision, "name": entry.name,
        "url": entry.url, "license": entry.license, "created_at": entry.created_at,
    }
    statement = (
        sqlite_insert(pool_entries)
        .values(slug=entry.id, **values)
        .on_conflict_do_update(index_elements=[pool_entries.c.slug], set_=values)
        .returning(pool_entries.c.pk)
    )
    return connection.execute(statement).scalar_one()


def _replace_entry_files(connection: Connection, entry_pk: int, files: list[PoolFile]) -> None:
    connection.execute(delete(pool_files).where(pool_files.c.entry_pk == entry_pk))
    if files:
        connection.execute(insert(pool_files), [
            {"entry_pk": entry_pk, "path": f.path, "position": i, "size": f.size, "checksum": f.checksum,
             "ready": f.ready, "mtime_ns": f.mtime_ns}
            for i, f in enumerate(files)
        ])
