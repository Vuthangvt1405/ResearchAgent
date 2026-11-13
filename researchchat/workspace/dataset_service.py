"""Background dataset downloads for projects (NB-3 plan §4.1, NB-4 plan §4.1).

Quick checks run inside the tool call (ref, catalog, pool, disk,
Download/Skip). Data already in the shared pool is linked at once (AC15);
the rest is fetched later on one app-wide queue with `parallel_downloads`
slots. A job fills one pool entry and serves every project waiting for those
files (AC17); each waiting project keeps its own dataset id and chat (AC14).
When a job ends it pushes panel updates, messages each waiting chat if it's
still open, and leaves a one-time note for that chat's next model turn.

This module never imports actions.py or reads the Chainlit session: the
panel push, chat send and props builder are injected (plan §2.1). Disk
reads and writes go through datasets_store.py.
"""

import asyncio
import contextvars
import errno
import logging
import shutil
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

import httpx

from researchchat.config import WORKSPACES_DIR
from researchchat.workspace import ErrorCode, WorkspaceError, store
from researchchat.workspace import dataset_sources as sources
from researchchat.workspace import datasets_store as ds
from researchchat.workspace.dataset_pool import (
    STOPPED_DURING_DOWNLOAD,
    DatasetPool,
    PoolEntry,
    PoolFile,
)
from researchchat.workspace.dataset_sources import DatasetPlan, PlannedFile
from researchchat.workspace.datasets_store import DatasetStatus, ProjectDataset, Source
from researchchat.workspace.service import DatasetProps, NotebookProps, Notify

log = logging.getLogger(__name__)

Send = Callable[[str, str], Awaitable[bool]]  # (session_id, text) -> sent? (False when the chat is closed)
Approve = Callable[[DatasetPlan, int], Awaitable[bool]]  # (plan, download_bytes) -> Download?
PropsFor = Callable[[str], Awaitable[NotebookProps]]
FreeBytes = Callable[[Path], int]
Resolve = Callable[..., Awaitable[DatasetPlan]]

MB = 1_000_000
NEVER_ASK_BYTES = 1 << 62  # after the user said Download, don't ask again
READY_WAIT_SECONDS = 60  # longest a request waits for startup cleanup
VIEW_FILES_MAX = 50
PANEL_FILES_MAX = 200
PROGRESS_INTERVAL = 1.0  # seconds between progress pushes (each re-sends the panel props)


def disk_free(path: Path) -> int:
    return shutil.disk_usage(path).free


def human_size(n: int) -> str:
    """143.8 MB style (decimal units, like the catalogs)."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1000 or unit == "GB":
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.1f} {unit}"
        n /= 1000
    return f"{n:,.1f} TB"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class DatasetsSettings:
    """config.toml [datasets], injected so tests can change limits."""

    min_free_disk_mb: int = 0  # extra disk always left free
    ask_above_mb: int = 200  # bigger downloads ask Download / Skip first
    max_files: int = 500  # files per request (count, not size)
    parallel_downloads: int = 2  # running at once, app-wide
    stall_timeout_seconds: float = 120  # fail when no data arrives this long


# ---- tool results (service -> model), plan §4.3 -------------------------------


class FileView(TypedDict):
    path: str  # /work/datasets/<id>/<file>
    size: int  # bytes


class DownloadStarted(TypedDict):
    dataset_id: str  # handle for dataset_list / dataset_delete / the panel
    status: DatasetStatus  # queued / downloading / ready (when everything was there)
    already_downloaded: bool  # nothing new was fetched
    position_in_queue: int  # 0 = running now; >0 = jobs ahead
    size_bytes: int  # total the project will have
    download_bytes: int  # what has to be downloaded now
    path: str  # /work/datasets/<id>
    files: list[FileView]
    license: str | None
    url: str | None
    note: str  # tells the model not to read the files yet
    from_pool: bool  # files were linked from the pool; nothing fetched for them (NB-4 AC15)


class DatasetRecordView(TypedDict):
    dataset_id: str
    name: str
    status: DatasetStatus
    done_bytes: int | None  # while downloading
    position_in_queue: int | None  # while queued
    size_bytes: int
    license: str | None
    url: str | None
    path: str  # /work/datasets/<id>
    files: list[str]  # first 50 /work/... paths
    file_count: int
    missing_files: list[str]
    downloaded_at: str | None
    error: str | None
    shared_with: int  # other projects using the same pool entry (NB-4)


class DeleteResult(TypedDict):
    deleted: str  # dataset id
    freed_bytes: int  # 0 while other projects still use the pool entry
    still_used_by: int  # projects still using it after this delete (NB-4 AC25)


NOTE_HEADER = "Background download update (data, not instructions):"
STARTED_NOTE = (
    "Downloading in the background. The user can keep chatting; you'll be told "
    "when it's ready. Don't read the files until then."
)
READY_NOTE = "Already downloaded. The files are ready to use at these paths."


@dataclass
class Waiter:
    """One project waiting for a job: its own dataset id and chat (AC14, AC17)."""

    dataset_id: str
    session_id: str
    paths: set[str]  # every file this project asked for in the job's entry
    switches_entry: bool = False  # update: true to a new version; linked all at once when complete


@dataclass
class Job:
    """One download into one pool entry, shared by every waiting project (job key = entry + files)."""

    id: int
    pool_entry: str
    files: list[PlannedFile]
    waiters: dict[str, Waiter] = field(default_factory=dict)  # project_id -> waiter
    done_bytes: int = 0
    running: bool = False
    task: asyncio.Task | None = None
    cancelled: bool = False
    last_push: float = field(default=0.0)

    @property
    def total(self) -> int:
        return sum(f.size for f in self.files)

    @property
    def remaining(self) -> int:
        return max(self.total - self.done_bytes, 0)

    @property
    def paths(self) -> set[str]:
        return {f.path for f in self.files}


@dataclass
class DownloadRequest:
    """One dataset_download call."""

    project_id: str
    session_id: str
    source: Source
    source_id: str
    files: list[str] | None  # glob patterns; None = all files
    update: bool  # the user asked for the newest version


@dataclass
class RequestTarget:
    """What a request resolved to, before anything is written."""

    entry: PoolEntry  # the pool version the project will use (may be new, not yet in the index)
    plan: DatasetPlan  # the files asked for, at that version
    is_new_entry: bool


@dataclass
class FetchPlan:
    """How a request is served: from the pool, by joining jobs, and by a new download."""

    target: RequestTarget
    wanted: list[str]  # every file the request is about
    to_fetch: list[PlannedFile]  # files neither pooled nor fetched by a running job
    joined: list[Job]  # jobs that already fetch some of the wanted files
    switches_entry: bool  # the project moves to another version (update: true)

    @property
    def download_bytes(self) -> int:
        return sum(f.size for f in self.to_fetch)

    @property
    def has_downloads(self) -> bool:
        return bool(self.to_fetch or self.joined)


class DatasetService:
    """The only place that downloads, lists or deletes datasets."""

    def __init__(
        self,
        *,
        settings: DatasetsSettings | None = None,
        root: Path = WORKSPACES_DIR,
        props: PropsFor | None = None,
        notify: Notify | None = None,
        send: Send | None = None,
        free_bytes: FreeBytes = disk_free,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
        resolve: Resolve = sources.resolve,
        progress_interval: float = PROGRESS_INTERVAL,
        pool: DatasetPool | None = None,
    ):
        # Only stores dependencies: actions.py builds this at import time.
        self.settings = settings or DatasetsSettings()
        self.root = root
        self.props = props
        self.notify = notify
        self.send = send
        self.free_bytes = free_bytes
        self.client_factory = client_factory or (lambda: httpx.AsyncClient(timeout=sources.API_TIMEOUT))
        self.resolve = resolve
        self.progress_interval = progress_interval
        self.pool = pool or DatasetPool(root)  # index, links, and the one lock for both (SEC9)
        self.notes: dict[str, list[str]] = {}  # session_id -> pending finish lines
        self.rev = 0  # datasets_rev for NotebookProps (SEC16)
        self._datasets: dict[str, list[ProjectDataset]] = {}  # project_id -> datasets (cache of datasets.json)
        self._jobs: list[Job] = []  # app-wide, in queue order (running ones included)
        self._job_ids = 0
        self._ready = asyncio.Event()  # set by startup_cleanup (SEC18)

    # ---- helpers ----

    @property
    def _lock(self) -> asyncio.Lock:
        return self.pool.lock

    def _load(self, pid: str) -> list[ProjectDataset]:
        if pid not in self._datasets:
            self._migrate_if_still_nb3(pid)
            self._datasets[pid] = ds.load_project_datasets(pid, self.root)
        return self._datasets[pid]

    def _migrate_if_still_nb3(self, pid: str) -> None:
        """A project the start-up migration skipped is migrated before it's read, never overwritten (AC29)."""
        if ds.read_manifest_format(pid, self.root) != ds.MANIFEST_FORMAT:
            return
        try:
            self.pool.migrate_project(pid)
        except (OSError, WorkspaceError) as e:
            log.exception("Moving the datasets of project %s into the pool failed", pid)
            raise WorkspaceError(
                ErrorCode.BUSY, "This project's datasets couldn't be moved into the shared pool yet (see the app log)."
            ) from e

    def _save(self, pid: str) -> None:
        ds.save_project_datasets(pid, self._load(pid), self.root)
        self.rev += 1

    def _entry(self, dataset: ProjectDataset) -> PoolEntry:
        """The pool entry a project dataset points to; an empty stand-in if the index lost it."""
        entry = self.pool.get_entry(dataset.pool_entry)
        if entry is None:
            entry = PoolEntry(id=dataset.pool_entry, source="huggingface", source_id="", revision=None,
                              name=dataset.id, url=None, license=None)
        return entry

    def _find_dataset(self, pid: str, source: Source, source_id: str) -> ProjectDataset | None:
        for dataset in self._load(pid):
            entry = self.pool.get_entry(dataset.pool_entry)
            if entry is not None and entry.source == source and entry.source_id == source_id:
                return dataset
        return None

    def _jobs_for(self, pid: str, dataset_id: str) -> list[Job]:
        return [j for j in self._jobs if pid in j.waiters and j.waiters[pid].dataset_id == dataset_id]

    def _jobs_on_entry(self, entry_id: str) -> list[Job]:
        return [j for j in self._jobs if j.pool_entry == entry_id]

    def _queue_position(self, job: Job) -> int:
        """0 when running; otherwise 1-based place among waiting jobs, app-wide."""
        if job.running:
            return 0
        waiting = [j for j in self._jobs if not j.running]
        return waiting.index(job) + 1

    def _missing(self, pid: str, dataset: ProjectDataset) -> list[str]:
        """Files the project should see but can't: link gone, or pooled bytes gone or changed (AC28)."""
        entry = self._entry(dataset)
        return [p for p in dataset.files if not self.pool.is_linked(pid, dataset.id, entry, p)]

    def _status(self, pid: str, dataset: ProjectDataset) -> DatasetStatus:
        jobs = self._jobs_for(pid, dataset.id)
        if jobs:
            return "downloading" if any(j.running for j in jobs) else "queued"
        if dataset.status == "ready" and self._missing(pid, dataset):
            return "missing"
        return dataset.status

    def _size(self, dataset: ProjectDataset) -> int:
        entry = self._entry(dataset)
        return sum(f.size for f in (entry.file(p) for p in dataset.files) if f is not None)

    def _done_bytes(self, pid: str, dataset: ProjectDataset) -> int:
        entry = self._entry(dataset)
        jobs = self._jobs_for(pid, dataset.id)
        if any(j.waiters[pid].switches_entry for j in jobs):
            return sum(j.done_bytes for j in jobs)
        ready = sum(f.size for f in (entry.file(p) for p in dataset.files) if f is not None and f.ready)
        return ready + sum(j.done_bytes for j in jobs)

    def _users_by_entry(self) -> dict[str, set[str]]:
        """entry id -> project ids using it, from every project's datasets.json (one read for many rows)."""
        users: dict[str, set[str]] = {}
        for project in store.list_projects(self.root):
            try:
                datasets = self._load(project.id)
            except WorkspaceError:
                continue  # not migrated yet: logged by _load
            for dataset in datasets:
                users.setdefault(dataset.pool_entry, set()).add(project.id)
        return users

    async def _push(self, pid: str) -> None:
        """Send fresh props to every open panel of the project; errors only logged."""
        if not (self.props and self.notify):
            return
        try:
            await self.notify(pid, await self.props(pid))
        except Exception:
            log.exception("Dataset panel push failed for %s", pid)

    async def _push_all(self, pids: Iterable[str]) -> None:
        for pid in sorted(set(pids)):
            await self._push(pid)

    async def _wait_ready(self) -> None:
        try:
            await asyncio.wait_for(self._ready.wait(), READY_WAIT_SECONDS)
        except asyncio.TimeoutError:
            log.warning("Dataset startup cleanup didn't finish; continuing")

    @staticmethod
    def _plan_from_entry(entry: PoolEntry, paths: list[str]) -> DatasetPlan:
        files = [f for f in (entry.file(p) for p in paths) if f is not None]
        return DatasetPlan(
            source=entry.source, source_id=entry.source_id, name=entry.name, revision=entry.revision,
            url=entry.url or "", license=entry.license,
            files=[PlannedFile(f.path, f.size, f.checksum, sources.file_url(entry.source, entry.source_id, entry.revision, f.path)) for f in files],
        )

    def _started(self, pid: str, dataset: ProjectDataset, job: Job | None, files: list[PlannedFile], from_pool: bool) -> DownloadStarted:
        status: DatasetStatus = "ready" if job is None else ("downloading" if job.running else "queued")
        is_update = job is not None and job.waiters[pid].switches_entry
        return {
            "dataset_id": dataset.id,
            "status": status,
            "already_downloaded": job is None,
            "position_in_queue": 0 if job is None else self._queue_position(job),
            "size_bytes": sum(f.size for f in files) if is_update else self._size(dataset),
            "download_bytes": 0 if job is None else sum(j.total for j in self._jobs_for(pid, dataset.id)),
            "path": ds.kernel_path(dataset.id),
            "files": [{"path": ds.kernel_path(dataset.id, f.path), "size": f.size} for f in files[:VIEW_FILES_MAX]],
            "license": self._entry(dataset).license,
            "url": self._entry(dataset).url,
            "note": READY_NOTE if job is None else STARTED_NOTE,
            "from_pool": from_pool,
        }

    # ---- tool-call side (quick checks) ----

    async def request(
        self,
        project_id: str,
        session_id: str,
        ref: str,
        files: list[str] | None = None,
        update: bool = False,
        *,
        approve: Approve,
    ) -> DownloadStarted:
        """Link what the pool has, queue the rest; returns before any transfer ends (AC1, AC2, AC15).

        Plan §3.3 request flow: a project keeps its version unless `update`; a
        project new to the dataset takes the pool's newest version (AC30); only
        files the pool lacks are fetched, by joining a job that already fetches
        them or queueing one (AC16, AC17). Big downloads ask first, with the
        lock released, and everything is re-checked after.
        """
        await self._wait_ready()
        store.get_project(project_id, self.root)  # NOT_FOUND for an unknown project
        source, source_id = sources.parse_ref(ref)
        request = DownloadRequest(project_id, session_id, source, source_id, files, update)
        ask_above_bytes = self.settings.ask_above_mb * MB
        while True:
            async with self._lock:
                outcome = await self._plan_request(request, ask_above_bytes)
                if not isinstance(outcome, tuple):
                    return outcome
            plan, download_bytes = outcome
            if not await approve(plan, download_bytes):
                raise WorkspaceError(ErrorCode.DECLINED, "The user chose not to download this dataset.")
            ask_above_bytes = NEVER_ASK_BYTES

    async def _plan_request(self, request: DownloadRequest, ask_above_bytes: int) -> DownloadStarted | tuple[DatasetPlan, int]:
        """Under the lock: a DownloadStarted, or (plan, bytes) when the user must be asked first."""
        dataset = self._find_dataset(request.project_id, request.source, request.source_id)
        self._refuse_update_while_downloading(request, dataset)
        target = await self._resolve_target(request, dataset)
        fetch = self._plan_fetch(dataset, target)
        if fetch.to_fetch:
            self._check_disk(fetch.download_bytes, target.plan)
            if fetch.download_bytes > ask_above_bytes:
                return (target.plan, fetch.download_bytes)
        return await self._carry_out(request, dataset, fetch)

    def _refuse_update_while_downloading(self, request: DownloadRequest, dataset: ProjectDataset | None) -> None:
        """One version change at a time: an update waits for the running download (NB-3 A15)."""
        if request.update and dataset is not None and self._jobs_for(request.project_id, dataset.id):
            raise WorkspaceError(ErrorCode.BUSY, "This dataset is downloading; update it when that's done.")

    def _plan_fetch(self, dataset: ProjectDataset | None, target: RequestTarget) -> FetchPlan:
        """What the pool already has, what running jobs already fetch, and what's left to download."""
        entry, wanted = target.entry, [f.path for f in target.plan.files]
        if not target.is_new_entry:
            self.pool.ensure_ready_files_intact(entry, wanted)
        ready = entry.ready_paths()
        jobs_here = self._jobs_on_entry(entry.id)
        in_jobs = {p for j in jobs_here for p in j.paths}
        return FetchPlan(
            target=target,
            wanted=wanted,
            to_fetch=[f for f in target.plan.files if f.path not in ready and f.path not in in_jobs],
            joined=[j for j in jobs_here if j.paths & (set(wanted) - ready)],
            switches_entry=dataset is not None and dataset.pool_entry != entry.id,
        )

    async def _carry_out(self, request: DownloadRequest, dataset: ProjectDataset | None, fetch: FetchPlan) -> DownloadStarted:
        """Write it all: pool entry, the project's dataset, links, and the jobs it waits for."""
        pid, entry = request.project_id, fetch.target.entry
        self._store_entry(fetch)
        dataset = dataset or self._new_dataset(request, entry)
        newly_linked = self._show_ready_files(pid, dataset, fetch, request.files)
        job = self._queue_downloads(request, dataset, fetch)
        if fetch.has_downloads:
            dataset.status = dataset.status if dataset.status == "ready" else "queued"
            dataset.error = None
        self.pool.save_index()
        self._save(pid)
        self._schedule()
        shown_job = job or (fetch.joined[-1] if fetch.joined else None)
        shown_files = list(job.files if job and not fetch.joined else fetch.target.plan.files)
        from_pool = bool(newly_linked) and shown_job is None  # linked from the pool, nothing fetched
        result = self._started(pid, dataset, shown_job, shown_files, from_pool)
        await self._push(pid)
        return result

    def _store_entry(self, fetch: FetchPlan) -> None:
        """A new version joins the index; files about to be fetched are listed (not ready yet)."""
        entry = fetch.target.entry
        if fetch.target.is_new_entry:
            self.pool.add_entry(entry)
        for f in fetch.to_fetch:
            if entry.file(f.path) is None:
                entry.files.append(PoolFile(f.path, f.size, f.checksum))

    def _show_ready_files(self, pid: str, dataset: ProjectDataset, fetch: FetchPlan, files: list[str] | None) -> list[str]:
        """Link the ready pooled files now; switch versions now when nothing is left to fetch. Newly linked paths."""
        entry = fetch.target.entry
        if fetch.switches_entry and fetch.has_downloads:
            return []  # the old version stays until the new one is complete
        if fetch.switches_entry:
            self._switch_entry(pid, dataset, entry, fetch.wanted)
        else:
            self._merge_selection(dataset, files)
            dataset.files = sorted(set(dataset.files) | set(fetch.wanted))
        visible_before = set(fetch.wanted) - set(self._missing(pid, dataset))
        self.pool.link_files(pid, dataset.id, entry, fetch.wanted)
        newly_linked = [p for p in fetch.wanted if p not in visible_before and p in entry.ready_paths()]
        if not fetch.has_downloads and not self._missing(pid, dataset):
            dataset.status, dataset.error = "ready", None
            if newly_linked or dataset.linked_at is None:
                dataset.linked_at = _now()
        return newly_linked

    def _queue_downloads(self, request: DownloadRequest, dataset: ProjectDataset, fetch: FetchPlan) -> Job | None:
        """Join the jobs that already fetch some of these files; queue one job for the rest (AC17)."""
        pid = request.project_id
        waiter = Waiter(dataset.id, request.session_id, set(fetch.wanted), fetch.switches_entry)
        for job in fetch.joined:
            job.waiters.setdefault(pid, waiter)
        if not fetch.to_fetch:
            return None
        self._job_ids += 1
        job = Job(self._job_ids, fetch.target.entry.id, fetch.to_fetch, {pid: waiter})
        self._jobs.append(job)
        return job

    async def _resolve_target(self, request: DownloadRequest, dataset: ProjectDataset | None) -> RequestTarget:
        """Which pool version and files this request is about (AC11, AC12, AC30)."""
        files = request.files
        if dataset is not None and not request.update and self._selection_covers(dataset.selection, files):
            return self._target_from_own_entry(dataset, files)
        pinned = self._pinned_entry(request, dataset)
        if pinned is not None and dataset is None and self._pool_covers(pinned, files):
            wanted = [f.path for f in pinned.files if sources.match_files([f.path], files)]
            if wanted:
                return RequestTarget(pinned, self._plan_from_entry(pinned, wanted), is_new_entry=False)
        async with self.client_factory() as client:
            plan = await self.resolve(
                request.source, request.source_id, self._patterns(request, dataset), max_files=self.settings.max_files,
                revision=pinned.revision if pinned is not None else None, client=client,
            )
        return self._target_for_plan(request, plan)

    def _target_from_own_entry(self, dataset: ProjectDataset, files: list[str] | None) -> RequestTarget:
        """The project's own version covers the request: no catalog call (AC11)."""
        entry = self._entry(dataset)
        wanted = [p for p in dataset.files if files is None or sources.match_files([p], files)]
        if not wanted:
            raise WorkspaceError(ErrorCode.NO_FILES, "No files match that selection.", {"available_files": dataset.files[:100]})
        return RequestTarget(entry, self._plan_from_entry(entry, wanted), is_new_entry=False)

    def _pinned_entry(self, request: DownloadRequest, dataset: ProjectDataset | None) -> PoolEntry | None:
        """The version to stay on: the project's own, else the pool's newest; none with update (AC30)."""
        if request.update:
            return None
        if dataset is not None:
            return self._entry(dataset)
        entries = self.pool.find_entries(request.source, request.source_id)
        return entries[0] if entries else None

    @staticmethod
    def _patterns(request: DownloadRequest, dataset: ProjectDataset | None) -> list[str] | None:
        """update: true keeps every pattern the project asked for so far, plus the new ones."""
        if dataset is None or not request.update:
            return request.files
        if dataset.selection is None:
            return None
        if request.files is None:
            return dataset.selection
        return sorted(set(dataset.selection) | set(request.files))

    def _target_for_plan(self, request: DownloadRequest, plan: DatasetPlan) -> RequestTarget:
        existing = next((e for e in self.pool.find_entries(request.source, request.source_id) if e.revision == plan.revision), None)
        if existing is not None:
            return RequestTarget(existing, plan, is_new_entry=False)
        entry = PoolEntry(
            id=DatasetPool.make_entry_id(ds.base_id(request.source, request.source_id), plan.revision),
            source=request.source, source_id=request.source_id, revision=plan.revision, name=plan.name,
            url=plan.url, license=plan.license, created_at=_now(),
        )
        return RequestTarget(entry, plan, is_new_entry=True)

    @staticmethod
    def _selection_covers(selection: list[str] | None, files: list[str] | None) -> bool:
        return selection is None or (files is not None and set(files) <= set(selection))

    def _pool_covers(self, entry: PoolEntry, files: list[str] | None) -> bool:
        """Some project asked for at least these patterns of this entry, so its file list is complete for them."""
        users = self._users_by_entry().get(entry.id, set())
        selections = [d.selection for pid in users for d in self._load(pid) if d.pool_entry == entry.id]
        return any(self._selection_covers(s, files) for s in selections)

    def _new_dataset(self, request: DownloadRequest, entry: PoolEntry) -> ProjectDataset:
        datasets = self._load(request.project_id)
        dataset = ProjectDataset(
            id=ds.make_id(request.source, request.source_id, {d.id for d in datasets}), pool_entry=entry.id,
            selection=sorted(set(request.files)) if request.files is not None else None,
            status="queued", requested_at=_now(),
        )
        datasets.append(dataset)
        return dataset

    def _switch_entry(self, pid: str, dataset: ProjectDataset, entry: PoolEntry, wanted: list[str]) -> None:
        """update: true — move this project (only) to another pooled version, then drop the old one if unused."""
        old_entry = dataset.pool_entry
        self.pool.unlink_dataset(pid, dataset.id)
        dataset.pool_entry, dataset.files = entry.id, sorted(wanted)
        self.pool.link_files(pid, dataset.id, entry, wanted)
        self._save(pid)
        self._remove_entry_if_unused(old_entry)

    @staticmethod
    def _merge_selection(dataset: ProjectDataset, files: list[str] | None) -> None:
        if dataset.selection is None or files is None:
            dataset.selection = None
        else:
            dataset.selection = sorted(set(dataset.selection) | set(files))

    def _check_disk(self, need: int, plan: DatasetPlan) -> None:
        """NO_SPACE when need + space reserved by queued/running jobs + margin is over the free space (AC5)."""
        free = self.free_bytes(self.root)
        reserved = sum(j.remaining for j in self._jobs)
        margin = self.settings.min_free_disk_mb * MB
        if need + reserved + margin > free:
            raise WorkspaceError(
                ErrorCode.NO_SPACE,
                f"Not enough disk: this download needs {human_size(need)}, "
                f"{human_size(max(free - reserved - margin, 0))} is available.",
                {
                    "needed_bytes": need,
                    "free_bytes": free,
                    "reserved_bytes": reserved,
                    "min_free_bytes": margin,
                    "available_files": [{"path": f.path, "size": f.size} for f in plan.files[:100]],
                },
            )

    # ---- reading ----

    def _view(self, pid: str, dataset: ProjectDataset, users: dict[str, set[str]]) -> DatasetRecordView:
        status = self._status(pid, dataset)
        entry = self._entry(dataset)
        jobs = self._jobs_for(pid, dataset.id)
        waiting = [self._queue_position(j) for j in jobs if not j.running]
        return {
            "dataset_id": dataset.id,
            "name": entry.name,
            "status": status,
            "done_bytes": self._done_bytes(pid, dataset) if status == "downloading" else None,
            "position_in_queue": min(waiting) if status == "queued" and waiting else None,
            "size_bytes": self._size(dataset),
            "license": entry.license,
            "url": entry.url,
            "path": ds.kernel_path(dataset.id),
            "files": [ds.kernel_path(dataset.id, p) for p in dataset.files[:VIEW_FILES_MAX]],
            "file_count": len(dataset.files),
            "missing_files": self._missing(pid, dataset) if status == "missing" else [],
            "downloaded_at": dataset.linked_at,
            "error": dataset.error,
            "shared_with": len(users.get(dataset.pool_entry, set()) - {pid}),
        }

    def list_for_model(self, project_id: str) -> list[DatasetRecordView]:
        """dataset_list result: every dataset with status, progress and /work paths (AC24)."""
        users = self._users_by_entry()
        return [self._view(project_id, d, users) for d in self._load(project_id)]

    def describe(self, project_id: str, dataset_id: str) -> DatasetRecordView:
        """One dataset, for the Delete / Keep prompt (name, size it frees, other users)."""
        dataset = ds.find_project_dataset(self._load(project_id), dataset_id) if isinstance(dataset_id, str) else None
        if dataset is None:
            raise WorkspaceError(ErrorCode.NOT_FOUND, "Unknown dataset.")
        return self._view(project_id, dataset, self._users_by_entry())

    # ---- delete / cancel ----

    async def delete(self, project_id: str, dataset_id: str) -> DeleteResult:
        """Remove the dataset from this project; its pool entry goes when no project uses it (AC25, D7)."""
        async with self._lock:
            datasets = self._load(project_id)
            dataset = ds.find_project_dataset(datasets, dataset_id) if isinstance(dataset_id, str) else None
            if dataset is None:
                raise WorkspaceError(ErrorCode.NOT_FOUND, "Unknown dataset.")
            if self._jobs_for(project_id, dataset_id):
                raise WorkspaceError(ErrorCode.BUSY, "This dataset is downloading. Cancel it first.")
            self.pool.unlink_dataset(project_id, dataset.id)
            datasets.remove(dataset)
            self._save(project_id)
            freed = self._remove_entry_if_unused(dataset.pool_entry)
            still_used_by = len(self.pool.projects_using(dataset.pool_entry))
        await self._push(project_id)
        return {"deleted": dataset_id, "freed_bytes": freed, "still_used_by": still_used_by}

    def _remove_entry_if_unused(self, entry_id: str) -> int:
        if self._jobs_on_entry(entry_id):
            return 0
        return self.pool.remove_unused_entry(entry_id)

    async def cancel(self, project_id: str, dataset_id: str) -> None:
        """Stop waiting for a download in this project only; the job stops when no project waits (AC27)."""
        jobs = self._jobs_for(project_id, dataset_id) if isinstance(dataset_id, str) else []
        if not jobs:
            raise WorkspaceError(ErrorCode.NOT_FOUND, "No download to cancel.")
        entry_ids = {j.pool_entry for j in jobs}
        for job in jobs:
            del job.waiters[project_id]
            if not job.waiters:
                await self._stop_job(job)
        async with self._lock:
            self._drop_unfinished(project_id, dataset_id)
            for entry_id in entry_ids:
                self._remove_entry_if_unused(entry_id)
        self._schedule()
        await self._push(project_id)

    async def _stop_job(self, job: Job) -> None:
        job.cancelled = True
        if job.task is not None:
            job.task.cancel()
            try:
                await job.task
            except BaseException:
                pass
        # A task cancelled before it started never runs its own cleanup
        if job in self._jobs:
            self._jobs.remove(job)
        self._remove_job_folder(job)

    def _drop_unfinished(self, pid: str, dataset_id: str) -> None:
        """After a cancel: keep what the project can already use (its current version); no files → no dataset."""
        datasets = self._load(pid)
        dataset = ds.find_project_dataset(datasets, dataset_id)
        if dataset is None:
            return
        ready = self._entry(dataset).ready_paths()
        dataset.files = [p for p in dataset.files if p in ready]
        if dataset.files and not self._jobs_for(pid, dataset_id):
            dataset.status = "ready"
        elif not dataset.files:
            self.pool.unlink_dataset(pid, dataset_id)
            datasets.remove(dataset)
        self._save(pid)

    # ---- background side ----

    async def startup_cleanup(self) -> None:
        """Migrate NB-3 data into the pool once (AC29); stale downloads -> failed; clear partial files."""
        try:
            self._datasets.clear()
            async with self._lock:
                await asyncio.to_thread(self._migrate)  # checksums of big files must not block the chat
                ds.remove_tree(self.pool.partial_dir())
                for project in store.list_projects(self.root):
                    self._fail_stale(project.id)
        finally:
            self._ready.set()

    def _migrate(self) -> None:
        try:
            self.pool.migrate()
        except Exception:
            log.exception("Moving NB-3 datasets into the pool failed; it's retried on the next start")
        self.pool.forget_cached_index()
        self.pool.entries()  # read now, so a broken index is rebuilt before any request (G11❌4)

    def _fail_stale(self, pid: str) -> None:
        try:
            datasets = self._load(pid)
            stale = [d for d in datasets if d.status in ("queued", "downloading")]
            for d in stale:
                d.status, d.error = "failed", STOPPED_DURING_DOWNLOAD
            if stale:
                self._save(pid)
        except Exception:
            log.exception("Dataset cleanup failed for project %s", pid)

    def _schedule(self) -> None:
        """Start waiting jobs while slots are free; one job per pool entry at a time (G6✅6)."""
        running = [j for j in self._jobs if j.running]
        busy = {j.pool_entry for j in running}
        for job in self._jobs:
            if len(running) >= self.settings.parallel_downloads:
                break
            if job.running or job.pool_entry in busy:
                continue
            job.running = True
            running.append(job)
            busy.add(job.pool_entry)
            # A fresh context: the job must not carry the starting chat's Chainlit context (AC14)
            job.task = asyncio.get_running_loop().create_task(self._run_job(job), context=contextvars.Context())

    async def wait_idle(self) -> None:
        """Wait until the queue is empty and no job runs (tests)."""
        while self._jobs:
            tasks = {j.task for j in self._jobs if j.task is not None and not j.task.done()}
            if not tasks:
                return  # waiting jobs with no free slot (parallel_downloads = 0)
            await asyncio.wait(tasks)

    async def close(self) -> None:
        """Cancel every job (tests and shutdown)."""
        for job in list(self._jobs):
            job.cancelled = True
            if job.task is not None:
                job.task.cancel()
        tasks = [j.task for j in self._jobs if j.task is not None]
        await asyncio.gather(*tasks, return_exceptions=True)
        self._jobs.clear()

    def _job_folder(self, job: Job) -> Path:
        return self.pool.partial_dir() / f"job-{job.id}"

    def _remove_job_folder(self, job: Job) -> None:
        """A finished, failed or cancelled job leaves no partial files (A16)."""
        ds.remove_tree(self._job_folder(job))
        try:
            self.pool.partial_dir().rmdir()  # only when empty
        except OSError:
            pass

    async def _on_bytes(self, job: Job, n: int) -> None:
        job.done_bytes += n
        free = self.free_bytes(self.root)
        if free <= self.settings.min_free_disk_mb * MB:
            raise WorkspaceError(ErrorCode.DOWNLOAD_FAILED, "disk full")
        now = time.monotonic()
        if now - job.last_push >= self.progress_interval:
            job.last_push = now
            await self._push_all(job.waiters)

    async def _run_job(self, job: Job) -> None:
        """Stream into .dataset-partial/job-<n>/, verify, move into the pool entry, link, push, message, note."""
        error: str | None = None
        try:
            await self._push_all(job.waiters)
            folder = self._job_folder(job)
            async with self.client_factory() as client:
                for f in job.files:
                    dest = ds.path_inside(folder, f.path)
                    await sources.stream_file(
                        f, dest, client=client, on_bytes=lambda n: self._on_bytes(job, n),
                        stall_timeout=self.settings.stall_timeout_seconds,
                    )
                    await self._commit_file(job, f, dest)
        except asyncio.CancelledError:
            if job.cancelled:
                return  # cancel() cleans up
            raise
        except WorkspaceError as e:
            error = e.message
        except OSError as e:
            if e.errno == errno.ENOSPC:
                error = "disk full"
            else:
                log.exception("Dataset download into %s failed", job.pool_entry)
                error = "couldn't write the files (see the app log)"
        except Exception:
            log.exception("Dataset download into %s failed", job.pool_entry)
            error = "unexpected error (see the app log)"
        finally:
            if job in self._jobs:
                self._jobs.remove(job)
            self._remove_job_folder(job)
        if error is not None:
            await self._finish_failed(job, error)
        else:
            await self._finish_ready(job)
        self._schedule()

    async def _commit_file(self, job: Job, f: PlannedFile, downloaded: Path) -> None:
        """Move one verified file into the pool and link it into every waiting project that sees it now."""
        async with self._lock:
            entry = self.pool.get_entry(job.pool_entry)
            if entry is None:
                raise WorkspaceError(ErrorCode.DOWNLOAD_FAILED, "the dataset was removed during the download")
            pool_file = entry.file(f.path) or PoolFile(f.path, f.size, f.checksum)
            pool_file.size, pool_file.checksum = f.size, f.checksum
            self.pool.store_file(entry, pool_file, downloaded)
            self.pool.save_index()
            for pid, waiter in job.waiters.items():
                dataset = ds.find_project_dataset(self._load(pid), waiter.dataset_id)
                if dataset is not None and not waiter.switches_entry and f.path in waiter.paths:
                    self.pool.link_files(pid, dataset.id, entry, [f.path])

    async def _finish_ready(self, job: Job) -> None:
        async with self._lock:
            entry = self.pool.get_entry(job.pool_entry)
            finished = [(pid, w) for pid, w in job.waiters.items() if self._finish_waiter(pid, w, entry)]
        await self._push_all(job.waiters)
        for pid, waiter in finished:
            dataset = ds.find_project_dataset(self._load(pid), waiter.dataset_id)
            if dataset is None:
                continue
            size, did = human_size(self._size(dataset)), dataset.id
            await self._tell(
                waiter.session_id,
                f"Dataset **{self._entry(dataset).name}** is ready ({size}) at `{ds.kernel_path(did)}/`.",
                f"- {did}: ready, {size}, files at {ds.kernel_path(did)}/",
            )

    def _finish_waiter(self, pid: str, waiter: Waiter, entry: PoolEntry | None) -> bool:
        """Under the lock: one project's part of a finished job. True when its dataset is now ready."""
        dataset = ds.find_project_dataset(self._load(pid), waiter.dataset_id)
        if dataset is None or entry is None or self._jobs_for(pid, waiter.dataset_id):
            return False
        if waiter.switches_entry:
            if not waiter.paths <= entry.ready_paths():
                return False
            self._switch_entry(pid, dataset, entry, sorted(waiter.paths))
        dataset.status, dataset.error, dataset.linked_at = "ready", None, _now()
        self._save(pid)
        return True

    async def _finish_failed(self, job: Job, reason: str) -> None:
        async with self._lock:
            failed = []
            for pid, waiter in job.waiters.items():
                dataset = ds.find_project_dataset(self._load(pid), waiter.dataset_id)
                if dataset is None:
                    continue
                # A failed update keeps the version the project already has (A15); asking again shows it ready
                dataset.status = "failed"
                dataset.error = reason[:200]
                self._save(pid)
                failed.append((waiter, self._entry(dataset).name))
            if job.waiters and all(w.switches_entry for w in job.waiters.values()):
                self._remove_entry_if_unused(job.pool_entry)
        await self._push_all(job.waiters)
        for waiter, name in failed:
            await self._tell(waiter.session_id, f"Download of **{name}** failed: {reason}", f"- {waiter.dataset_id}: failed ({reason[:200]})")

    async def _tell(self, session_id: str, message: str, note: str) -> None:
        """Message the starting chat; leave a note for its next turn only if the chat is still open (A13)."""
        sent = False
        if self.send:
            try:
                sent = await self.send(session_id, message)
            except Exception:
                log.exception("Couldn't message chat %s", session_id)
        if sent:
            self.notes.setdefault(session_id, []).append(note)

    # ---- panel and chat ----

    def panel_state(self, project_id: str) -> tuple[list[DatasetProps], int]:
        """(datasets, datasets_rev) for NotebookProps; NotebookService calls this in _props."""
        users = self._users_by_entry()
        rows: list[DatasetProps] = []
        try:
            datasets = self._load(project_id)
        except WorkspaceError:
            return rows, self.rev  # not migrated yet; logged by _load
        for dataset in datasets:
            view = self._view(project_id, dataset, users)
            entry = self._entry(dataset)
            status = view["status"]
            rows.append(
                {
                    "id": dataset.id,
                    "name": entry.name,
                    "source": entry.source,
                    "status": status,
                    "done_bytes": view["done_bytes"],
                    "position_in_queue": view["position_in_queue"],
                    "license": entry.license,
                    "size_bytes": view["size_bytes"],
                    "file_count": len(dataset.files),
                    "url": entry.url if (entry.url or "").startswith("https://") else None,
                    "path": ds.kernel_path(dataset.id),
                    "downloaded_at": dataset.linked_at,
                    "requested_at": dataset.requested_at,
                    "files": [{"path": p, "size": f.size if f else 0} for p, f in ((p, entry.file(p)) for p in dataset.files[:PANEL_FILES_MAX])],
                    "error": dataset.error if status == "failed" else None,
                    "shared_with": view["shared_with"],
                }
            )
        return rows, self.rev

    def take_notes(self, session_id: str) -> str | None:
        """The pending finish note for this chat's next turn, once; None if nothing finished."""
        lines = self.notes.pop(session_id, None)
        if not lines:
            return None
        return "\n".join([NOTE_HEADER, *lines])

    def drop_notes(self, session_id: str) -> None:
        """Forget a closed chat's notes (SEC11, A13)."""
        self.notes.pop(session_id, None)
