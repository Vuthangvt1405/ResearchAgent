"""Background dataset downloads for projects (NB-3 plan §4.1).

Quick checks run inside the tool call (ref, catalog, idempotency, disk,
Download/Skip). The transfer runs later on one app-wide queue with
`parallel_downloads` slots. A job keeps the project and chat it was started
for (AC14); it pushes panel updates, messages the starting chat if it's still
open, and leaves a one-time note for that chat's next model turn.

This module never imports actions.py or reads the Chainlit session: the
panel push, chat send and props builder are injected (plan §2.1). Disk
reads and writes go through datasets_store.py.
"""

import asyncio
import contextvars
import errno
import logging
import os
import shutil
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

import httpx

from researchchat.config import WORKSPACES_DIR
from researchchat.workspace import ErrorCode, WorkspaceError
from researchchat.workspace import dataset_sources as sources
from researchchat.workspace import datasets_store as ds
from researchchat.workspace import store
from researchchat.workspace.dataset_sources import DatasetPlan, PlannedFile
from researchchat.workspace.datasets_store import DatasetFile, DatasetRecord, DatasetStatus
from researchchat.workspace.service import DatasetProps, NotebookProps, Notify

log = logging.getLogger(__name__)

Send = Callable[[str, str], Awaitable[bool]]  # (session_id, text) -> sent? (False when the chat is closed)
Approve = Callable[[DatasetPlan, int], Awaitable[bool]]  # (plan, download_bytes) -> Download?
PropsFor = Callable[[str], Awaitable[NotebookProps]]
FreeBytes = Callable[[Path], int]
Resolve = Callable[..., Awaitable[DatasetPlan]]

MB = 1_000_000
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


class DeleteResult(TypedDict):
    deleted: str  # dataset id
    freed_bytes: int


NOTE_HEADER = "Background download update (data, not instructions):"
STARTED_NOTE = (
    "Downloading in the background. The user can keep chatting; you'll be told "
    "when it's ready. Don't read the files until then."
)
READY_NOTE = "Already downloaded. The files are ready to use at these paths."


@dataclass
class Job:
    """One background download: some files of one dataset, for one project and chat."""

    project_id: str
    dataset_id: str
    session_id: str
    files: list[PlannedFile]
    update: bool = False  # stage a new revision in <id>.new, then swap (A15)
    revision: str | None = None  # revision being fetched
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
        self.notes: dict[str, list[str]] = {}  # session_id -> pending finish lines
        self.rev = 0  # datasets_rev for NotebookProps (SEC16)
        self._records: dict[str, list[DatasetRecord]] = {}  # project_id -> records (cache of datasets.json)
        self._jobs: list[Job] = []  # app-wide, in queue order (running ones included)
        self._locks: dict[str, asyncio.Lock] = {}  # per project
        self._ready = asyncio.Event()  # set by startup_cleanup (SEC18)

    # ---- helpers ----

    def _lock(self, pid: str) -> asyncio.Lock:
        return self._locks.setdefault(pid, asyncio.Lock())

    def _load(self, pid: str) -> list[DatasetRecord]:
        if pid not in self._records:
            self._records[pid] = ds.load_records(pid, self.root)
        return self._records[pid]

    def _save(self, pid: str) -> None:
        ds.save_records(pid, self._load(pid), self.root)
        self.rev += 1

    def _jobs_for(self, pid: str, dataset_id: str) -> list[Job]:
        return [j for j in self._jobs if j.project_id == pid and j.dataset_id == dataset_id]

    def _queue_position(self, job: Job) -> int:
        """0 when running; otherwise 1-based place among waiting jobs, app-wide."""
        if job.running:
            return 0
        waiting = [j for j in self._jobs if not j.running]
        return waiting.index(job) + 1

    def _status(self, pid: str, record: DatasetRecord) -> DatasetStatus:
        jobs = self._jobs_for(pid, record.id)
        if jobs:
            return "downloading" if any(j.running for j in jobs) else "queued"
        if record.status == "ready" and ds.missing_files(pid, record, self.root):
            return "missing"
        return record.status

    def _done_bytes(self, pid: str, record: DatasetRecord) -> int:
        ready = sum(f.size for f in record.files if f.ready)
        jobs = self._jobs_for(pid, record.id)
        if any(j.update for j in jobs):
            return sum(j.done_bytes for j in jobs)
        return ready + sum(j.done_bytes for j in jobs)

    async def _push(self, pid: str) -> None:
        """Send fresh props to every open panel of the project; errors only logged."""
        if not (self.props and self.notify):
            return
        try:
            await self.notify(pid, await self.props(pid))
        except Exception:
            log.exception("Dataset panel push failed for %s", pid)

    async def _wait_ready(self) -> None:
        try:
            await asyncio.wait_for(self._ready.wait(), READY_WAIT_SECONDS)
        except asyncio.TimeoutError:
            log.warning("Dataset startup cleanup didn't finish; continuing")

    def _plan_from_record(self, record: DatasetRecord, files: list[DatasetFile]) -> DatasetPlan:
        return DatasetPlan(
            source=record.source,
            source_id=record.source_id,
            name=record.name,
            revision=record.revision,
            url=record.url or "",
            license=record.license,
            files=[self._planned(record, f) for f in files],
        )

    @staticmethod
    def _planned(record: DatasetRecord, f: DatasetFile) -> PlannedFile:
        return PlannedFile(f.path, f.size, f.checksum, sources.file_url(record.source, record.source_id, record.revision, f.path))

    def _started(self, record: DatasetRecord, job: Job | None, files: list[DatasetFile] | list[PlannedFile]) -> DownloadStarted:
        status: DatasetStatus = "ready" if job is None else ("downloading" if job.running else "queued")
        return {
            "dataset_id": record.id,
            "status": status,
            "already_downloaded": job is None,
            "position_in_queue": 0 if job is None else self._queue_position(job),
            "size_bytes": record.size_bytes if job is None or not job.update else job.total,
            "download_bytes": 0 if job is None else job.total,
            "path": ds.kernel_path(record.id),
            "files": [{"path": ds.kernel_path(record.id, f.path), "size": f.size} for f in files[:VIEW_FILES_MAX]],
            "license": record.license,
            "url": record.url,
            "note": READY_NOTE if job is None else STARTED_NOTE,
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
        """Check and queue a download; returns before the transfer ends (AC1, AC2).

        Plan §3.3 idempotency: an existing dataset keeps its revision unless
        `update`; only files the project doesn't have yet are fetched; the
        disk check counts space reserved by every queued job; big downloads
        ask first, with the lock released, and everything is re-checked after.
        """
        await self._wait_ready()
        store.get_project(project_id, self.root)  # NOT_FOUND for an unknown project
        source, source_id = sources.parse_ref(ref)
        approved = False
        while True:
            async with self._lock(project_id):
                outcome = await self._plan_request(project_id, session_id, source, source_id, files, update, approved)
                if not isinstance(outcome, tuple):
                    return outcome
            plan, download_bytes = outcome
            if not await approve(plan, download_bytes):
                raise WorkspaceError(ErrorCode.DECLINED, "The user chose not to download this dataset.")
            approved = True

    async def _plan_request(self, pid, session_id, source, source_id, files, update, approved):
        """Under the project lock: a DownloadStarted, or (plan, bytes) when the user must be asked."""
        records = self._load(pid)
        record = next((r for r in records if r.source == source and r.source_id == source_id), None)
        covered = record is not None and (record.selection is None or (files is not None and set(files) <= set(record.selection)))

        if record is not None and covered and not update:
            # Keep the stored version; no catalog call (AC11, AC12)
            wanted = [f for f in record.files if files is None or sources.match_files([f.path], files)]
            missing = set(ds.missing_files(pid, record, self.root))
            planned = [self._planned(record, f) for f in wanted if not f.ready or f.path in missing]
            plan = self._plan_from_record(record, wanted)
            if not wanted:
                raise WorkspaceError(ErrorCode.NO_FILES, "No files match that selection.", {"available_files": [f.path for f in record.files][:100]})
        else:
            patterns = files
            if record is not None and update:
                patterns = None if record.selection is None or files is None else sorted(set(record.selection) | set(files))
                if files is None and record.selection is not None:
                    patterns = record.selection
            async with self.client_factory() as client:
                plan = await self.resolve(
                    source, source_id, patterns, max_files=self.settings.max_files,
                    revision=None if record is None or update else record.revision, client=client,
                )
            if record is not None and update and plan.revision != record.revision:
                return await self._queue_update(pid, session_id, record, plan, approved)
            have = {} if record is None else {f.path: f for f in record.files}
            missing = set() if record is None else set(ds.missing_files(pid, record, self.root))
            planned = [
                f for f in plan.files
                if not (f.path in have and have[f.path].ready and f.path not in missing
                        and have[f.path].size == f.size and have[f.path].checksum == f.checksum)
            ]

        # Files another job of this dataset already fetches are not fetched twice (SEC9)
        jobs = self._jobs_for(pid, record.id) if record else []
        in_jobs = {f.path for j in jobs for f in j.files}
        to_fetch = [f for f in planned if f.path not in in_jobs]
        if record is not None and not to_fetch:
            if jobs and planned:
                return self._started(record, jobs[-1], jobs[-1].files)
            self._merge_selection(record, files)
            if not jobs and all(f.ready for f in record.files) and not ds.missing_files(pid, record, self.root):
                # e.g. a failed update: the stored version is complete again
                record.status, record.error = "ready", None
            self._save(pid)
            return self._started(record, None, [f for f in record.files if files is None or sources.match_files([f.path], files)])

        need = sum(f.size for f in to_fetch)
        self._check_disk(pid, need, plan)
        if need > self.settings.ask_above_mb * MB and not approved:
            return (plan, need)

        if record is None:
            record = DatasetRecord(
                id=ds.make_id(source, source_id, records), name=plan.name, source=source, source_id=source_id,
                revision=plan.revision, url=plan.url, license=plan.license,
                selection=sorted(set(files)) if files is not None else None, status="queued", requested_at=_now(),
            )
            records.append(record)
        else:
            self._merge_selection(record, files)
            record.error = None
            if record.status == "failed":
                record.status = "queued"
        have = {f.path: f for f in record.files}
        for f in to_fetch:
            have[f.path] = DatasetFile(f.path, f.size, f.checksum, False)
        record.files = list(have.values())
        job = Job(pid, record.id, session_id, to_fetch, revision=record.revision)
        return await self._enqueue(record, job)

    async def _queue_update(self, pid, session_id, record, plan, approved):
        """update: true and a newer revision: stage every selected file of it in <id>.new (AC12, A15)."""
        if self._jobs_for(pid, record.id):
            raise WorkspaceError(ErrorCode.BUSY, "This dataset is downloading; update it when that's done.")
        need = sum(f.size for f in plan.files)
        self._check_disk(pid, need, plan)
        if need > self.settings.ask_above_mb * MB and not approved:
            return (plan, need)
        job = Job(pid, record.id, session_id, list(plan.files), update=True, revision=plan.revision)
        return await self._enqueue(record, job)

    async def _enqueue(self, record: DatasetRecord, job: Job) -> DownloadStarted:
        if record.status != "ready":
            record.status = "queued"
        self._jobs.append(job)
        self._save(job.project_id)
        self._schedule()
        result = self._started(record, job, job.files)
        await self._push(job.project_id)
        return result

    @staticmethod
    def _merge_selection(record: DatasetRecord, files: list[str] | None) -> None:
        if record.selection is None or files is None:
            record.selection = None
        else:
            record.selection = sorted(set(record.selection) | set(files))

    def _check_disk(self, pid: str, need: int, plan: DatasetPlan) -> None:
        """NO_SPACE when need + space reserved by queued/running jobs + margin is over the free space (AC5)."""
        free = self.free_bytes(store.project_dir(pid, self.root))
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

    def _view(self, pid: str, record: DatasetRecord) -> DatasetRecordView:
        status = self._status(pid, record)
        jobs = self._jobs_for(pid, record.id)
        waiting = [self._queue_position(j) for j in jobs if not j.running]
        return {
            "dataset_id": record.id,
            "name": record.name,
            "status": status,
            "done_bytes": self._done_bytes(pid, record) if status == "downloading" else None,
            "position_in_queue": min(waiting) if status == "queued" and waiting else None,
            "size_bytes": record.size_bytes,
            "license": record.license,
            "url": record.url,
            "path": ds.kernel_path(record.id),
            "files": [ds.kernel_path(record.id, f.path) for f in record.files[:VIEW_FILES_MAX]],
            "file_count": len(record.files),
            "missing_files": ds.missing_files(pid, record, self.root) if status == "missing" else [],
            "downloaded_at": record.downloaded_at,
            "error": record.error,
        }

    def list_for_model(self, project_id: str) -> list[DatasetRecordView]:
        """dataset_list result: every dataset with status, progress and /work paths (AC24)."""
        return [self._view(project_id, r) for r in self._load(project_id)]

    def describe(self, project_id: str, dataset_id: str) -> DatasetRecordView:
        """One dataset, for the Delete / Keep prompt (name and size it frees)."""
        record = ds.find_record(self._load(project_id), dataset_id) if isinstance(dataset_id, str) else None
        if record is None:
            raise WorkspaceError(ErrorCode.NOT_FOUND, "Unknown dataset.")
        return self._view(project_id, record)

    # ---- delete / cancel ----

    async def delete(self, project_id: str, dataset_id: str) -> DeleteResult:
        """Remove files/datasets/<id>/ and its record; BUSY while downloading (AC25)."""
        async with self._lock(project_id):
            records = self._load(project_id)
            record = ds.find_record(records, dataset_id) if isinstance(dataset_id, str) else None
            if record is None:
                raise WorkspaceError(ErrorCode.NOT_FOUND, "Unknown dataset.")
            if self._jobs_for(project_id, dataset_id):
                raise WorkspaceError(ErrorCode.BUSY, "This dataset is downloading. Cancel it first.")
            freed = sum(f.size for f in record.files if f.ready)
            ds.remove_dataset_dir(project_id, record.id, self.root)
            records.remove(record)
            self._save(project_id)
        await self._push(project_id)
        return {"deleted": dataset_id, "freed_bytes": freed}

    async def cancel(self, project_id: str, dataset_id: str) -> None:
        """Stop a running or queued job; remove partial files; drop the unfinished part (AC27, A3)."""
        jobs = self._jobs_for(project_id, dataset_id) if isinstance(dataset_id, str) else []
        if not jobs:
            raise WorkspaceError(ErrorCode.NOT_FOUND, "No download to cancel.")
        for job in jobs:
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
        async with self._lock(project_id):
            ds.remove_partial(project_id, dataset_id, self.root)
            records = self._load(project_id)
            record = ds.find_record(records, dataset_id)
            if record is not None:
                record.files = [f for f in record.files if f.ready]
                if record.files:
                    record.status = "ready"
                else:
                    ds.remove_dataset_dir(project_id, dataset_id, self.root)
                    records.remove(record)
            self._save(project_id)
        self._schedule()
        await self._push(project_id)

    # ---- background side ----

    async def startup_cleanup(self) -> None:
        """queued/downloading records -> failed ("app stopped during download"); recover swaps; clear partials."""
        try:
            self._records.clear()
            for project in store.list_projects(self.root):
                try:
                    ds.recover_partials(project.id, self.root)
                    records = self._load(project.id)
                    stale = [r for r in records if r.status in ("queued", "downloading")]
                    for r in stale:
                        r.status, r.error = "failed", "app stopped during download"
                    if stale:
                        self._save(project.id)
                except Exception:
                    log.exception("Dataset cleanup failed for project %s", project.id)
        finally:
            self._ready.set()

    def _schedule(self) -> None:
        """Start waiting jobs while slots are free; one job per dataset at a time (G6✅6)."""
        running = [j for j in self._jobs if j.running]
        busy = {(j.project_id, j.dataset_id) for j in running}
        for job in self._jobs:
            if len(running) >= self.settings.parallel_downloads:
                break
            if job.running or (job.project_id, job.dataset_id) in busy:
                continue
            job.running = True
            running.append(job)
            busy.add((job.project_id, job.dataset_id))
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

    async def _on_bytes(self, job: Job, n: int) -> None:
        job.done_bytes += n
        free = self.free_bytes(store.project_dir(job.project_id, self.root))
        if free <= self.settings.min_free_disk_mb * MB:
            raise WorkspaceError(ErrorCode.DOWNLOAD_FAILED, "disk full")
        now = time.monotonic()
        if now - job.last_push >= self.progress_interval:
            job.last_push = now
            await self._push(job.project_id)

    async def _run_job(self, job: Job) -> None:
        """Stream into .dataset-partial/, re-check disk, verify, move in, push, message, note."""
        pid, did = job.project_id, job.dataset_id
        error: str | None = None
        try:
            await self._push(pid)
            folder = ds.partial_dir(pid, did, ".new" if job.update else "", self.root)
            async with self.client_factory() as client:
                for f in job.files:
                    dest = ds.file_path(pid, did, f.path, self.root, folder=folder)
                    await sources.stream_file(
                        f, dest, client=client, on_bytes=lambda n: self._on_bytes(job, n),
                        stall_timeout=self.settings.stall_timeout_seconds,
                    )
                    if not job.update:
                        await self._commit_file(job, f, dest)
            if job.update:
                await self._commit_update(job)
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
                log.exception("Dataset download %s/%s failed", pid, did)
                error = "couldn't write the files (see the app log)"
        except Exception:
            log.exception("Dataset download %s/%s failed", pid, did)
            error = "unexpected error (see the app log)"
        finally:
            if job in self._jobs:
                self._jobs.remove(job)
        if error is not None:
            await self._finish_failed(job, error)
        else:
            await self._finish_ready(job)
        self._schedule()

    async def _commit_file(self, job: Job, f: PlannedFile, src: Path) -> None:
        async with self._lock(job.project_id):
            final = ds.file_path(job.project_id, job.dataset_id, f.path, self.root)
            final.parent.mkdir(parents=True, exist_ok=True)
            os.replace(src, final)
            record = ds.find_record(self._load(job.project_id), job.dataset_id)
            if record is not None:
                for rf in record.files:
                    if rf.path == f.path:
                        rf.size, rf.checksum, rf.ready = f.size, f.checksum, True
                self._save(job.project_id)

    async def _commit_update(self, job: Job) -> None:
        async with self._lock(job.project_id):
            ds.swap_in_update(job.project_id, job.dataset_id, self.root)
            record = ds.find_record(self._load(job.project_id), job.dataset_id)
            if record is not None:
                record.revision = job.revision
                record.files = [DatasetFile(f.path, f.size, f.checksum, True) for f in job.files]
                self._save(job.project_id)

    async def _finish_ready(self, job: Job) -> None:
        pid, did = job.project_id, job.dataset_id
        async with self._lock(pid):
            ds.remove_partial(pid, did, self.root)
            record = ds.find_record(self._load(pid), did)
            if record is None:
                return
            if not self._jobs_for(pid, did):
                record.status = "ready"
            record.downloaded_at, record.error = _now(), None
            self._save(pid)
        await self._push(pid)
        size = human_size(record.size_bytes)
        await self._tell(
            job.session_id,
            f"Dataset **{record.name}** is ready ({size}) at `{ds.kernel_path(did)}/`.",
            f"- {did}: ready, {size}, files at {ds.kernel_path(did)}/",
        )

    async def _finish_failed(self, job: Job, reason: str) -> None:
        pid, did = job.project_id, job.dataset_id
        async with self._lock(pid):
            ds.remove_partial(pid, did, self.root)
            record = ds.find_record(self._load(pid), did)
            if record is None:
                return
            record.status, record.error = "failed", reason[:200]
            self._save(pid)
        await self._push(pid)
        await self._tell(job.session_id, f"Download of **{record.name}** failed: {reason}", f"- {did}: failed ({reason[:200]})")

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
        rows: list[DatasetProps] = []
        for record in self._load(project_id):
            view = self._view(project_id, record)
            status = view["status"]
            rows.append(
                {
                    "id": record.id,
                    "name": record.name,
                    "source": record.source,
                    "status": status,
                    "done_bytes": view["done_bytes"],
                    "position_in_queue": view["position_in_queue"],
                    "license": record.license,
                    "size_bytes": record.size_bytes,
                    "file_count": len(record.files),
                    "url": record.url if (record.url or "").startswith("https://") else None,
                    "path": ds.kernel_path(record.id),
                    "downloaded_at": record.downloaded_at,
                    "requested_at": record.requested_at,
                    "files": [{"path": f.path, "size": f.size} for f in record.files[:PANEL_FILES_MAX]],
                    "error": record.error if status == "failed" else None,
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
