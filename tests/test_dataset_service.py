"""Tests for DatasetService: disk check, approval, background jobs, idempotency,
delete/cancel, panel props and chat notes (NB-3 plan §7: G4–G7, G9, G10, S❌4, S❌6).

No network (MockTransport), fake host lookups, fake free disk, fake chat send,
tmp_path disk. Each test runs one asyncio.run(scenario()); background jobs are
awaited with wait_idle().
"""

import asyncio
import hashlib
import json

import httpx
import pytest

from researchchat.workspace import ErrorCode, WorkspaceError
from researchchat.workspace import actions
from researchchat.workspace import dataset_sources as src
from researchchat.workspace import datasets_store as ds
from researchchat.workspace import store
from researchchat.workspace.dataset_service import DatasetService, DatasetsSettings
from researchchat.workspace.dataset_sources import DatasetPlan, PlannedFile
from researchchat.workspace.service import NotebookService
from tests.conftest import FakeChats, FakeFreeDisk, FakeKernels, fake_lookup

GB = 1_000_000_000
MB = 1_000_000
R1, R2 = "1" * 40, "2" * 40


@pytest.fixture(autouse=True)
def no_dns(monkeypatch):
    monkeypatch.setattr(src, "lookup_host", fake_lookup)


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "ws"
    store.create_project("P1", root, project_id="p1")
    store.create_project("P2", root, project_id="p2")
    return root


def run(coro):
    return asyncio.run(coro)


async def yes(plan, size):
    return True


async def no(plan, size):
    return False


class Catalog:
    """A fake Hugging Face: repos -> {revision: {path: bytes}}, with per-file behaviours.

    behaviours[path]: "wrong" (same length, other bytes), "error" (transport error),
    "extra" (twice the bytes), "stall", "block" (waits for `gate`), "redirect" (CDN hop),
    "redirect_private", "loop" (endless redirects). `fail_once` paths fail the first time.
    """

    def __init__(self, files=None, repo="org/name", revision=R1):
        self.repos = {repo: {"sha": revision, "revs": {revision: dict(files or {"a.csv": b"a,b\n1,2\n", "b.csv": b"x\n" * 50})}}}
        self.behaviours: dict[str, str] = {}
        self.fail_once: set[str] = set()
        self.requested: list[httpx.Request] = []
        self.gate = asyncio.Event()

    def add_repo(self, repo, files, revision=R1):
        self.repos[repo] = {"sha": revision, "revs": {revision: dict(files)}}

    def new_revision(self, repo, revision, files):
        self.repos[repo]["sha"] = revision
        self.repos[repo]["revs"][revision] = dict(files)

    def file_requests(self, path=None):
        return [r for r in self.requested if "/resolve/" in r.url.path and (path is None or r.url.path.endswith("/" + path))]

    def api_requests(self):
        return [r for r in self.requested if r.url.path.startswith("/api/")]

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requested.append(request)
        host, path = request.url.host, request.url.path
        if host != "huggingface.co":
            return httpx.Response(200, content=self._cdn_body)
        if path.startswith("/api/datasets/"):
            rest = path[len("/api/datasets/"):]
            for repo, data in self.repos.items():
                if rest == repo:
                    return httpx.Response(200, json={"id": repo, "sha": data["sha"], "private": False, "gated": False, "cardData": {"license": "mit", "pretty_name": "Secret Pretty Name"}})
                if rest.startswith(repo + "/tree/"):
                    rev = rest.split("/tree/")[1]
                    files = data["revs"][rev]
                    return httpx.Response(200, json=[
                        {"type": "file", "path": p, "size": len(b), "lfs": {"oid": hashlib.sha256(b).hexdigest(), "size": len(b)}}
                        for p, b in files.items()
                    ])
            return httpx.Response(404)
        if "/resolve/" in path:
            repo = path[len("/datasets/"):].split("/resolve/")[0]
            rev, fpath = path.split("/resolve/")[1].split("/", 1)
            body = self.repos[repo]["revs"][rev][fpath]
            how = self.behaviours.get(fpath)
            if fpath in self.fail_once:
                self.fail_once.discard(fpath)
                raise httpx.ConnectError("boom")
            if how == "wrong":
                return httpx.Response(200, content=bytes(len(body)))
            if how == "error":
                raise httpx.ConnectError("boom")
            if how == "extra":
                return httpx.Response(200, content=body * 2)
            if how == "stall":
                return httpx.Response(200, content=self._stall(body))
            if how == "block":
                return httpx.Response(200, content=self._blocked(body))
            if how == "redirect":
                self._cdn_body = body
                return httpx.Response(307, headers={"location": "https://cas-bridge.xethub.hf.co/x?sig=1"})
            if how == "redirect_private":
                return httpx.Response(307, headers={"location": self.private_target})
            if how == "loop":
                n = int(request.url.params.get("n", "0"))
                return httpx.Response(307, headers={"location": f"{request.url.copy_with(params={'n': n + 1})}"})
            return httpx.Response(200, content=body)
        return httpx.Response(404)

    async def _stall(self, body):
        yield body[:1]
        await asyncio.sleep(5)
        yield body[1:]

    async def _blocked(self, body):
        await self.gate.wait()
        yield body


class Env:
    def __init__(self, root, catalog=None, free=100 * GB, **settings):
        self.root = root
        self.catalog = catalog or Catalog()
        self.disk = FakeFreeDisk(free)
        self.chats = FakeChats(open_sessions=("s1", "s2"))
        self.pushes: list[tuple[str, dict]] = []
        defaults = dict(min_free_disk_mb=0, ask_above_mb=200, max_files=500, parallel_downloads=2, stall_timeout_seconds=0.2)
        defaults.update(settings)
        self.resolve = None
        self.svc = None
        self.settings = DatasetsSettings(**defaults)

    async def start(self, resolve=None):
        kwargs = {"resolve": resolve} if resolve else {}
        self.svc = DatasetService(
            settings=self.settings, root=self.root, props=self.props, notify=self.notify, send=self.chats.send,
            free_bytes=self.disk, client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(self.catalog)),
            progress_interval=0, **kwargs,
        )
        await self.svc.startup_cleanup()
        return self.svc

    async def props(self, pid):
        rows, rev = self.svc.panel_state(pid)
        return {"datasets": json.loads(json.dumps(rows)), "datasets_rev": rev}

    async def notify(self, pid, props):
        self.pushes.append((pid, props))

    def folder(self, pid, dataset_id="hf-org--name"):
        return ds.dataset_dir(pid, dataset_id, self.root)

    def partial(self, pid):
        return ds.partial_root(pid, self.root)


async def until(cond, timeout=2.0):
    """Wait (briefly) for a background state."""
    for _ in range(int(timeout / 0.005)):
        if cond():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("condition not reached")


def fake_plan(size, name="Big data", license="mit", source_id="org/name"):
    return DatasetPlan("huggingface", source_id, name, R1, f"https://huggingface.co/datasets/{source_id}", license,
                       [PlannedFile("data.csv", size, None, f"https://huggingface.co/datasets/{source_id}/resolve/{R1}/data.csv")])


def fake_resolver(*plans):
    by_id = {p.source_id: p for p in plans}
    calls = []

    async def resolve(source, source_id, files=None, *, max_files, revision=None, client=None):
        calls.append(source_id)
        return by_id[source_id]

    resolve.calls = calls
    return resolve


class Approver:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    async def __call__(self, plan, size):
        self.calls.append((plan.name, size, plan.license, len(plan.files)))
        return self.answer


# ---- Group 4 — Disk check and approval (AC5, AC6, AC7, SEC3, SEC4) · unit
# Baseline: Given a 50 MB plan, an empty project and 100 GB free · When request(pid, ref, approve=fake)
# (parallel_downloads = 0 keeps queued jobs from starting, so nothing big is streamed)


def test_small_download_starts_without_asking(root):
    # G4✅1 · Then: approve not called; job queued · Demonstrates: small downloads just start
    async def scenario():
        env = Env(root, parallel_downloads=0)
        svc = await env.start(fake_resolver(fake_plan(50 * MB)))
        approve = Approver(True)
        started = await svc.request("p1", "s1", "hf:org/name", approve=approve)
        assert approve.calls == []
        assert started["status"] == "queued" and started["download_bytes"] == 50 * MB
        assert len(svc._jobs) == 1

    run(scenario())


def test_big_download_asks_and_starts_on_yes(root):
    # G4✅2 · Changed: 300 MB, approve → True · Then: approve called once with name, size, licence; job queued
    # Demonstrates: you decide on big downloads
    async def scenario():
        env = Env(root, parallel_downloads=0)
        svc = await env.start(fake_resolver(fake_plan(300 * MB)))
        approve = Approver(True)
        started = await svc.request("p1", "s1", "hf:org/name", approve=approve)
        assert approve.calls == [("Big data", 300 * MB, "mit", 1)]
        assert started["status"] == "queued" and len(svc._jobs) == 1

    run(scenario())


def test_no_size_cap_when_disk_has_room(root):
    # G4✅3 · Changed: 50 GB plan, 100 GB free · Then: job queued (after approval) · Demonstrates: only the disk limits size
    async def scenario():
        env = Env(root, parallel_downloads=0)
        svc = await env.start(fake_resolver(fake_plan(50 * GB)))
        started = await svc.request("p1", "s1", "hf:org/name", approve=yes)
        assert started["status"] == "queued" and started["download_bytes"] == 50 * GB

    run(scenario())


def test_declined_download_writes_nothing(root):
    # G4❌1 · Changed: 300 MB, approve → False · Then: DECLINED; no record, no job, nothing on disk
    # Demonstrates: Skip means nothing happens
    async def scenario():
        env = Env(root, parallel_downloads=0)
        svc = await env.start(fake_resolver(fake_plan(300 * MB)))
        with pytest.raises(WorkspaceError) as e:
            await svc.request("p1", "s1", "hf:org/name", approve=no)
        assert e.value.code == ErrorCode.DECLINED
        assert svc.list_for_model("p1") == [] and svc._jobs == []
        assert not ds.manifest_path("p1", root).exists()
        assert not (store.project_dir("p1", root) / "files" / "datasets").exists()

    run(scenario())


def test_not_enough_disk_is_refused_before_asking(root):
    # G4❌2 · Changed: 50 GB plan, 40 GB free · Then: NO_SPACE with sizes + available_files; approve not called
    # Demonstrates: a download that can't fit never starts
    async def scenario():
        env = Env(root, free=40 * GB, parallel_downloads=0)
        svc = await env.start(fake_resolver(fake_plan(50 * GB)))
        approve = Approver(True)
        with pytest.raises(WorkspaceError) as e:
            await svc.request("p1", "s1", "hf:org/name", approve=approve)
        assert e.value.code == ErrorCode.NO_SPACE
        assert e.value.details["needed_bytes"] == 50 * GB and e.value.details["free_bytes"] == 40 * GB
        assert e.value.details["available_files"] == [{"path": "data.csv", "size": 50 * GB}]
        assert approve.calls == [] and svc._jobs == [] and svc.list_for_model("p1") == []

    run(scenario())


def test_queued_jobs_reserve_disk(root):
    # G4❌3 · Changed: 60 GB free, a 30 GB job queued, new 31 GB plan · Then: NO_SPACE (30 GB reserved shown)
    # Demonstrates: two downloads can't claim the same space
    async def scenario():
        env = Env(root, free=60 * GB, parallel_downloads=0)
        svc = await env.start(fake_resolver(fake_plan(30 * GB, source_id="org/a"), fake_plan(31 * GB, source_id="org/b")))
        await svc.request("p1", "s1", "hf:org/a", approve=yes)
        with pytest.raises(WorkspaceError) as e:
            await svc.request("p2", "s2", "hf:org/b", approve=yes)
        assert e.value.code == ErrorCode.NO_SPACE and e.value.details["reserved_bytes"] == 30 * GB
        assert len(svc._jobs) == 1

    run(scenario())


def test_disk_filling_during_download_fails_and_cleans_up(root):
    # G4❌4 · Changed: free disk hits 0 after chunk 1 · Then: failed ("disk full"); partial removed; message sent
    # Demonstrates: the disk is never filled to the end
    async def scenario():
        env = Env(root)
        svc = await env.start()
        real = env.catalog.__call__

        async def filling(request):
            response = await real(request)
            if "/resolve/" in request.url.path:
                env.disk.free = 0
            return response

        env.catalog.__call__ = filling
        svc.client_factory = lambda: httpx.AsyncClient(transport=httpx.MockTransport(filling))
        await svc.request("p1", "s1", "hf:org/name", approve=yes)
        await svc.wait_idle()
        [view] = svc.list_for_model("p1")
        assert view["status"] == "failed" and view["error"] == "disk full"
        assert not env.partial("p1").exists()
        assert env.chats.sent and "failed: disk full" in env.chats.sent[-1][1]

    run(scenario())


# ---- Group 5 — Download and verify (AC3, AC8, AC9, SEC1, SEC5) · integration
# Baseline: Given a queued job of 2 files with correct checksums · When the job runs (wait_idle)


async def download(env, files=None, update=False, session="s1", pid="p1"):
    started = await env.svc.request(pid, session, "hf:org/name", files, update, approve=yes)
    await env.svc.wait_idle()
    return started


def test_job_writes_files_and_marks_ready(root):
    # G5✅1 · Then: files in files/datasets/<id>/, record ready, .dataset-partial empty
    # Demonstrates: files end up where the tool said
    async def scenario():
        env = Env(root)
        await env.start()
        started = await download(env)
        assert started["path"] == "/work/datasets/hf-org--name"
        assert (env.folder("p1") / "a.csv").read_bytes() == b"a,b\n1,2\n"
        assert (env.folder("p1") / "b.csv").read_bytes() == b"x\n" * 50
        [record] = ds.load_records("p1", root)
        assert record.status == "ready" and all(f.ready for f in record.files) and record.downloaded_at
        assert not env.partial("p1").exists() or not any(env.partial("p1").iterdir())

    run(scenario())


def test_job_pushes_progress_to_panels(root):
    # G5✅2 · Then: downloading with rising done_bytes, then ready · Demonstrates: the panel shows live progress
    async def scenario():
        env = Env(root)
        await env.start()
        await download(env)
        rows = [p["datasets"][0] for pid, p in env.pushes if pid == "p1" and p["datasets"]]
        progress = [r["done_bytes"] for r in rows if r["status"] == "downloading" and r["done_bytes"]]
        assert progress == sorted(progress) and len(set(progress)) >= 2
        assert rows[-1]["status"] == "ready"
        revs = [p["datasets_rev"] for _, p in env.pushes]
        assert revs == sorted(revs)

    run(scenario())


def test_redirect_to_public_https_cdn_is_followed(root):
    # G5✅3 · Changed: 307 → https://cas-bridge… · Then: ready · Demonstrates: real HF downloads work
    async def scenario():
        env = Env(root)
        env.catalog.behaviours["a.csv"] = "redirect"
        await env.start()
        await download(env)
        assert ds.load_records("p1", root)[0].status == "ready"
        assert any(r.url.host == "cas-bridge.xethub.hf.co" for r in env.catalog.requested)

    run(scenario())


def test_checksum_mismatch_fails_and_cleans_up(root):
    # G5❌1 · Changed: wrong bytes · Then: failed (checksum); no files left · Demonstrates: corrupted data is never used
    async def scenario():
        env = Env(root)
        env.catalog.behaviours["a.csv"] = "wrong"
        await env.start()
        await download(env)
        [record] = ds.load_records("p1", root)
        assert record.status == "failed" and "checksum mismatch on a.csv" in record.error
        assert not (env.folder("p1") / "a.csv").exists()
        assert not env.partial("p1").exists()

    run(scenario())


def test_network_error_midway_cleans_up(root):
    # G5❌2 · Changed: transport raises on file 2 · Then: failed; no partial files
    # Demonstrates: broken downloads leave nothing half-done
    async def scenario():
        env = Env(root)
        env.catalog.behaviours["b.csv"] = "error"
        await env.start()
        await download(env)
        [record] = ds.load_records("p1", root)
        assert record.status == "failed" and "network error" in record.error
        assert not (env.folder("p1") / "b.csv").exists()
        assert not env.partial("p1").exists()

    run(scenario())


def test_redirect_to_private_address_is_blocked(root):
    # G5❌3 · Changed: 307 → http://127.0.0.1/, → https://10.0.0.1/ · Then: failed; never requested
    # Demonstrates: redirects can't reach your network
    for target in ("http://127.0.0.1/x", "https://10.0.0.1/x"):
        async def scenario():
            env = Env(root)
            env.catalog.behaviours["a.csv"] = "redirect_private"
            env.catalog.private_target = target
            await env.start()
            await download(env)
            record = ds.load_records("p1", root)[0]
            assert record.status == "failed" and "blocked" in record.error
            assert not any(r.url.host in ("127.0.0.1", "10.0.0.1") for r in env.catalog.requested)
            await env.svc.delete("p1", record.id)

        run(scenario())


def test_more_bytes_than_declared_aborts(root):
    # G5❌4 · Changed: 2× declared size · Then: failed; stream stopped · Demonstrates: a lying server can't fill the disk
    async def scenario():
        env = Env(root)
        env.catalog.behaviours["b.csv"] = "extra"
        await env.start()
        await download(env)
        record = ds.load_records("p1", root)[0]
        assert record.status == "failed" and "bigger than the catalog said" in record.error
        assert not (env.folder("p1") / "b.csv").exists()

    run(scenario())


def test_stalled_download_fails(root):
    # G5❌5 · Changed: no bytes for stall_timeout_seconds · Then: failed (stalled) · Demonstrates: stuck downloads end
    async def scenario():
        env = Env(root, stall_timeout_seconds=0.05)
        env.catalog.behaviours["a.csv"] = "stall"
        await env.start()
        await download(env)
        record = ds.load_records("p1", root)[0]
        assert record.status == "failed" and "stalled" in record.error

    run(scenario())


def test_too_many_redirects(root):
    # G5❌6 · Changed: 6 redirects · Then: failed · Demonstrates: no redirect loops
    async def scenario():
        env = Env(root)
        env.catalog.behaviours["a.csv"] = "loop"
        await env.start()
        await download(env)
        record = ds.load_records("p1", root)[0]
        assert record.status == "failed" and "too many redirects" in record.error
        assert len(env.catalog.file_requests("a.csv")) == src.MAX_REDIRECTS + 1

    run(scenario())


# ---- Group 6 — Idempotency and versions (AC11, AC12, AC28, SEC9) · unit
# Baseline: Given the project has a ready dataset (revision r1, files=["*.csv"]) · When requesting or reading again


def csv_parquet_catalog():
    return Catalog({"a.csv": b"1,2\n", "b.csv": b"3,4\n", "c.parquet": b"PAR1"})


def test_same_download_returns_existing(root):
    # G6✅1 · Changed: same request · Then: already_downloaded: true; no catalog or file request
    # Demonstrates: no wasted work
    async def scenario():
        env = Env(root, catalog=csv_parquet_catalog())
        await env.start()
        await download(env, ["*.csv"])
        before = len(env.catalog.requested)
        again = await download(env, ["*.csv"])
        assert again["already_downloaded"] is True and again["status"] == "ready"
        assert [f["path"] for f in again["files"]] == ["/work/datasets/hf-org--name/a.csv", "/work/datasets/hf-org--name/b.csv"]
        assert len(env.catalog.requested) == before

    run(scenario())


def test_newer_revision_is_not_used_without_update(root):
    # G6✅2 · Changed: catalog now at r2, no update · Then: r1 kept; no catalog call
    # Demonstrates: your data never changes unless you ask
    async def scenario():
        env = Env(root, catalog=csv_parquet_catalog())
        await env.start()
        await download(env, ["*.csv"])
        env.catalog.new_revision("org/name", R2, {"a.csv": b"new!", "b.csv": b"new!"})
        before = len(env.catalog.requested)
        again = await download(env, ["*.csv"])
        assert again["already_downloaded"] is True
        assert ds.load_records("p1", root)[0].revision == R1
        assert (env.folder("p1") / "a.csv").read_bytes() == b"1,2\n"
        assert len(env.catalog.requested) == before

    run(scenario())


def test_update_true_downloads_current_revision(root):
    # G6✅3 · Changed: catalog at r2, update: true · Then: job for the *.csv selection at r2;
    # old folder replaced only when complete; same /work path · Demonstrates: updating works and keeps paths
    async def scenario():
        env = Env(root, catalog=csv_parquet_catalog())
        await env.start()
        await download(env, ["*.csv"])
        env.catalog.new_revision("org/name", R2, {"a.csv": b"new-a", "b.csv": b"new-b", "c.parquet": b"PAR2"})
        env.catalog.behaviours["b.csv"] = "block"
        started = await env.svc.request("p1", "s1", "hf:org/name", None, True, approve=yes)
        assert started["path"] == "/work/datasets/hf-org--name"
        assert sorted(f["path"].rsplit("/", 1)[1] for f in started["files"]) == ["a.csv", "b.csv"]
        await until(lambda: env.catalog.file_requests("b.csv") and any("/" + R2 + "/" in r.url.path for r in env.catalog.file_requests("b.csv")))
        assert (env.folder("p1") / "a.csv").read_bytes() == b"1,2\n"  # old version still in place mid-update
        env.catalog.gate.set()
        await env.svc.wait_idle()
        record = ds.load_records("p1", root)[0]
        assert record.revision == R2 and record.status == "ready"
        assert (env.folder("p1") / "a.csv").read_bytes() == b"new-a"
        assert (env.folder("p1") / "b.csv").read_bytes() == b"new-b"
        assert not (env.folder("p1") / "c.parquet").exists()
        assert not env.partial("p1").exists()

    run(scenario())


def test_missing_files_show_missing_status(root):
    # G6✅4 · Changed: one file deleted from disk · Then: missing with that file · Demonstrates: the list tells the truth
    async def scenario():
        env = Env(root)
        await env.start()
        await download(env)
        (env.folder("p1") / "a.csv").unlink()
        [view] = env.svc.list_for_model("p1")
        assert view["status"] == "missing" and view["missing_files"] == ["a.csv"]

    run(scenario())


def test_new_selection_adds_only_new_files(root):
    # G6✅5 · Changed: files=["*.parquet"] · Then: same id and folder; job fetches only parquet; csv untouched;
    # selection = both · Demonstrates: selections never clash
    async def scenario():
        env = Env(root, catalog=csv_parquet_catalog())
        await env.start()
        await download(env, ["*.csv"])
        before = len(env.catalog.file_requests())
        started = await download(env, ["*.parquet"])
        assert started["dataset_id"] == "hf-org--name"
        assert [r.url.path.rsplit("/", 1)[1] for r in env.catalog.file_requests()[before:]] == ["c.parquet"]
        record = ds.load_records("p1", root)[0]
        assert record.selection == ["*.csv", "*.parquet"]
        assert sorted(p.name for p in env.folder("p1").iterdir()) == ["a.csv", "b.csv", "c.parquet"]

    run(scenario())


def test_new_selection_while_downloading_queues_after_it(root):
    # G6✅6 · Changed: first job running, then *.parquet · Then: second job waits for the first; folder ends with both
    # Demonstrates: no two jobs write one folder at once
    async def scenario():
        env = Env(root, catalog=csv_parquet_catalog())
        env.catalog.behaviours["b.csv"] = "block"
        svc = await env.start()
        first = await svc.request("p1", "s1", "hf:org/name", ["*.csv"], approve=yes)
        second = await svc.request("p1", "s1", "hf:org/name", ["*.parquet"], approve=yes)
        assert first["status"] == "downloading" and second["status"] == "queued"
        await asyncio.sleep(0.05)
        assert env.catalog.file_requests("c.parquet") == []
        env.catalog.gate.set()
        await svc.wait_idle()
        assert sorted(p.name for p in env.folder("p1").iterdir()) == ["a.csv", "b.csv", "c.parquet"]
        assert ds.load_records("p1", root)[0].status == "ready"

    run(scenario())


def test_failed_dataset_can_be_downloaded_again(root):
    # G6✅7 · Changed: failed on file 2 of 2 · Then: job fetches only file 2; ready · Demonstrates: retry without starting over
    async def scenario():
        env = Env(root)
        env.catalog.fail_once.add("b.csv")
        await env.start()
        await download(env)
        assert ds.load_records("p1", root)[0].status == "failed"
        before = len(env.catalog.file_requests())
        retry = await download(env)
        assert retry["download_bytes"] == len(b"x\n" * 50)
        assert [r.url.path.rsplit("/", 1)[1] for r in env.catalog.file_requests()[before:]] == ["b.csv"]
        assert ds.load_records("p1", root)[0].status == "ready"

    run(scenario())


def test_missing_files_are_downloaded_again_only(root):
    # G6✅8 · Changed: 1 of 3 files deleted, same request · Then: job fetches only that file
    # Demonstrates: re-downloading after cleanup is cheap
    async def scenario():
        env = Env(root, catalog=csv_parquet_catalog())
        await env.start()
        await download(env)
        (env.folder("p1") / "b.csv").unlink()
        before = len(env.catalog.file_requests())
        await download(env)
        assert [r.url.path.rsplit("/", 1)[1] for r in env.catalog.file_requests()[before:]] == ["b.csv"]
        assert env.svc.list_for_model("p1")[0]["status"] == "ready"

    run(scenario())


def test_same_dataset_while_running_returns_running_job(root):
    # G6❌2 · Changed: record downloading · Then: same id, downloading; no second job · Demonstrates: no double downloads
    async def scenario():
        env = Env(root)
        env.catalog.behaviours["b.csv"] = "block"
        svc = await env.start()
        first = await svc.request("p1", "s1", "hf:org/name", approve=yes)
        second = await svc.request("p1", "s2", "hf:org/name", approve=yes)
        assert second["dataset_id"] == first["dataset_id"] and second["status"] == "downloading"
        assert len(svc._jobs) == 1
        env.catalog.gate.set()
        await svc.wait_idle()

    run(scenario())


def test_startup_marks_stale_jobs_failed(root):
    # G6❌3 · Changed: records queued/downloading, files in .dataset-partial/ · Then: failed; partial cleared
    # Demonstrates: a crash leaves no half files
    def rec(id, status):
        return ds.DatasetRecord(id=id, name=id, source="zenodo", source_id=id[-1], revision=None, url=None, license=None,
                                selection=None, status=status, files=[ds.DatasetFile("x.csv", 3, None, False)])

    ds.save_records("p1", [rec("zenodo-1", "queued"), rec("zenodo-2", "downloading")], root)
    part = ds.partial_dir("p1", "zenodo-2", "", root)
    part.mkdir(parents=True)
    (part / "x.csv").write_text("ha")
    old = ds.partial_dir("p1", "zenodo-3", ".old", root)  # crash mid update-swap
    old.mkdir()
    (old / "y.csv").write_text("kept")

    async def scenario():
        env = Env(root)
        svc = await env.start()
        views = {v["dataset_id"]: v for v in svc.list_for_model("p1")}
        assert {k: (v["status"], v["error"]) for k, v in views.items()} == {
            "zenodo-1": ("failed", "app stopped during download"),
            "zenodo-2": ("failed", "app stopped during download"),
        }

    run(scenario())
    assert not ds.partial_root("p1", root).exists()
    assert (ds.dataset_dir("p1", "zenodo-3", root) / "y.csv").read_text() == "kept"


# ---- Group 7 — Delete and cancel (AC25, AC26, AC27, SEC4, SEC9) · unit
# Baseline: Given a ready dataset · When delete(pid, dataset_id)


def test_delete_removes_folder_and_record(root):
    # G7✅1 · Then: folder and record gone; freed_bytes = size; panels pushed · Demonstrates: delete frees the space
    async def scenario():
        env = Env(root)
        await env.start()
        await download(env)
        pushes = len(env.pushes)
        result = await env.svc.delete("p1", "hf-org--name")
        assert result == {"deleted": "hf-org--name", "freed_bytes": len(b"a,b\n1,2\n") + len(b"x\n" * 50)}
        assert not env.folder("p1").exists()
        assert ds.load_records("p1", root) == []
        assert len(env.pushes) > pushes and env.pushes[-1][1]["datasets"] == []

    run(scenario())


def test_cancel_running_or_queued_job_removes_it(root):
    # G7✅3 · Changed: own job downloading, then another queued · Then: stopped / never started; partial removed;
    # records removed · Demonstrates: you can stop a download at any point
    async def scenario():
        catalog = Catalog({"a.csv": b"aaa"})
        catalog.add_repo("org/other", {"o.csv": b"ooo"})
        catalog.behaviours["a.csv"] = "block"
        env = Env(root, catalog=catalog, parallel_downloads=1)
        svc = await env.start()
        await svc.request("p1", "s1", "hf:org/name", approve=yes)
        queued = await svc.request("p1", "s1", "hf:org/other", approve=yes)
        assert queued["status"] == "queued"
        await until(lambda: catalog.file_requests("a.csv"))
        # The queued one first: cancelling the running one frees its slot,
        # and the queued job would start (and maybe finish) right away
        await svc.cancel("p1", "hf-org--other")
        await svc.cancel("p1", "hf-org--name")
        await svc.wait_idle()
        assert svc._jobs == [] and svc.list_for_model("p1") == []
        assert catalog.file_requests("o.csv") == []
        assert not env.partial("p1").exists()
        assert not env.folder("p1").exists()

    run(scenario())


def test_delete_unknown_id_is_not_found(root):
    # G7❌1 · Changed: id not in the project · Then: NOT_FOUND; nothing removed
    async def scenario():
        env = Env(root)
        await env.start()
        await download(env)
        with pytest.raises(WorkspaceError) as e:
            await env.svc.delete("p1", "zenodo-404")
        assert e.value.code == ErrorCode.NOT_FOUND
        assert len(ds.load_records("p1", root)) == 1 and env.folder("p1").is_dir()

    run(scenario())


def test_delete_while_downloading_is_busy(root):
    # G7❌2 · Changed: record downloading · Then: BUSY; download continues · Demonstrates: no delete under a running download
    async def scenario():
        env = Env(root)
        env.catalog.behaviours["b.csv"] = "block"
        svc = await env.start()
        await svc.request("p1", "s1", "hf:org/name", approve=yes)
        with pytest.raises(WorkspaceError) as e:
            await svc.delete("p1", "hf-org--name")
        assert e.value.code == ErrorCode.BUSY
        env.catalog.gate.set()
        await svc.wait_idle()
        assert ds.load_records("p1", root)[0].status == "ready"

    run(scenario())


def test_model_delete_declined_keeps_dataset(root):
    # G7❌3 · Changed: tool, approve → False · Then: DECLINED; everything kept · Demonstrates: the model can't delete without you
    from researchchat.tools import dataset_delete

    async def scenario():
        env = Env(root)
        await env.start()
        await download(env)
        asked = []

        async def keep(name, size):
            asked.append((name, size))
            return False

        shown, result = await dataset_delete.run({"dataset_id": "hf-org--name"}, svc=env.svc, project_id="p1", approve=keep)
        assert json.loads(result)["error"] == ErrorCode.DECLINED
        assert asked == [("Secret Pretty Name", len(b"a,b\n1,2\n") + len(b"x\n" * 50))]
        assert len(ds.load_records("p1", root)) == 1 and (env.folder("p1") / "a.csv").is_file()

    run(scenario())


def test_cancel_when_not_downloading(root):
    # G7❌4 · Changed: record ready · Then: NOT_FOUND; dataset kept · Demonstrates: cancel never deletes finished data
    async def scenario():
        env = Env(root)
        await env.start()
        await download(env)
        with pytest.raises(WorkspaceError) as e:
            await env.svc.cancel("p1", "hf-org--name")
        assert e.value.code == ErrorCode.NOT_FOUND
        assert (env.folder("p1") / "a.csv").is_file() and len(ds.load_records("p1", root)) == 1

    run(scenario())


# ---- Group 9 — Panel actions and props (AC8, AC21, AC25, AC27) · unit
# Baseline: Given a session on project p1 with one ready dataset · When dispatch(svc, session, "ds_delete", {"dataset_id": id})


class FakeSession:
    def __init__(self, **values):
        self.values = dict(values)

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


async def panel_env(root, monkeypatch, catalog=None):
    env = Env(root, catalog=catalog)
    svc = await env.start()
    nb = NotebookService(FakeKernels(), root=root, datasets=svc.panel_state)
    monkeypatch.setattr(actions, "datasets", svc)
    return env, svc, nb, FakeSession(project_id="p1")


def test_ds_delete_returns_props_without_dataset(root, monkeypatch):
    # G9✅1 · Then: NotebookProps with datasets: [] · Demonstrates: the panel updates after delete
    async def scenario():
        env, svc, nb, session = await panel_env(root, monkeypatch)
        await download(env)
        assert len((await nb.props("p1"))["datasets"]) == 1
        props = await actions.dispatch(nb, session, "ds_delete", {"dataset_id": "hf-org--name"})
        assert props["datasets"] == [] and props["project"]["id"] == "p1" and "cells" in props

    run(scenario())


def test_props_show_status_and_licence_only_while_not_ready(root, monkeypatch):
    # G9✅2 · Changed: one downloading, one ready · Then: downloading row has status, done_bytes, license;
    # ready row has size_bytes, file_count; datasets_rev is higher · Demonstrates: the panel shows what matters at each stage
    async def scenario():
        catalog = Catalog({"a.csv": b"aaa"})
        catalog.add_repo("org/slow", {"s.csv": b"s" * 10})
        catalog.behaviours["s.csv"] = "block"
        env, svc, nb, session = await panel_env(root, monkeypatch, catalog)
        await download(env)
        rev_before = (await nb.props("p1"))["datasets_rev"]
        await svc.request("p1", "s1", "hf:org/slow", approve=yes)
        await until(lambda: catalog.file_requests("s.csv"))
        props = await nb.props("p1")
        rows = {r["id"]: r for r in props["datasets"]}
        slow, ready = rows["hf-org--slow"], rows["hf-org--name"]
        assert slow["status"] == "downloading" and slow["done_bytes"] == 0 and slow["license"] == "mit"
        assert ready["status"] == "ready" and ready["size_bytes"] == 3 and ready["file_count"] == 1
        assert ready["path"] == "/work/datasets/hf-org--name" and ready["url"].startswith("https://")
        assert props["datasets_rev"] > rev_before
        catalog.gate.set()
        await svc.wait_idle()

    run(scenario())


def test_ds_actions_bad_payload(root, monkeypatch):
    # G9❌1 · Changed: missing dataset_id, int id, extra project_id · Then: BAD_PAYLOAD for the first two; extra ignored
    # Demonstrates: the payload can't pick the project
    async def scenario():
        env, svc, nb, session = await panel_env(root, monkeypatch)
        await download(env)
        await download(env, pid="p2")
        for name in ("ds_delete", "ds_cancel"):
            for payload in ({}, {"dataset_id": 5}):
                with pytest.raises(WorkspaceError) as e:
                    await actions.dispatch(nb, session, name, payload)
                assert e.value.code == ErrorCode.BAD_PAYLOAD
        props = await actions.dispatch(nb, session, "ds_delete", {"dataset_id": "hf-org--name", "project_id": "p2"})
        assert props["project"]["id"] == "p1" and props["datasets"] == []
        assert len(ds.load_records("p2", root)) == 1 and env.folder("p2").is_dir()

    run(scenario())


def test_ds_delete_other_projects_dataset_is_not_found(root, monkeypatch):
    # G9❌2 · Changed: id only in p2 · Then: NOT_FOUND; p2 untouched · Demonstrates: no cross-project delete
    async def scenario():
        env, svc, nb, session = await panel_env(root, monkeypatch)
        await download(env, pid="p2")
        with pytest.raises(WorkspaceError) as e:
            await actions.dispatch(nb, session, "ds_delete", {"dataset_id": "hf-org--name"})
        assert e.value.code == ErrorCode.NOT_FOUND
        assert len(ds.load_records("p2", root)) == 1 and (env.folder("p2") / "a.csv").is_file()

    run(scenario())


# ---- Group 10 — Background jobs and chat (AC2, AC3, AC9, AC10, AC14, SEC10, SEC11) · unit
# Baseline: Given chat s1 on project p1 requests a 50 MB download · When the job runs while s1 keeps chatting


def test_finished_job_messages_the_starting_chat(root):
    # G10✅1 · Then: one message to s1: "Dataset X is ready … at /work/datasets/<id>/" · Demonstrates: you hear when it's done
    async def scenario():
        env = Env(root)
        await env.start()
        await download(env)
        assert env.chats.sent == [("s1", "Dataset **Secret Pretty Name** is ready (108 B) at `/work/datasets/hf-org--name/`.")]

    run(scenario())


def test_other_messages_are_handled_while_job_runs(root):
    # G10✅2 · Changed: a second message during the job · Then: it completes before the job ends
    # Demonstrates: chatting is never blocked
    async def scenario():
        env = Env(root)
        env.catalog.behaviours["b.csv"] = "block"
        svc = await env.start()
        started = await svc.request("p1", "s1", "hf:org/name", approve=yes)
        assert started["status"] == "downloading"
        views = await asyncio.wait_for(asyncio.to_thread(lambda: None), 1) or svc.list_for_model("p1")
        again = await asyncio.wait_for(svc.request("p1", "s1", "hf:org/name", approve=yes), 1)
        assert views[0]["status"] == "downloading" and again["status"] == "downloading"
        assert len(svc._jobs) == 1 and not svc._jobs[0].task.done()
        env.catalog.gate.set()
        await svc.wait_idle()

    run(scenario())


def test_finish_note_reaches_model_on_next_turn_once(root):
    # G10✅3 · Changed: job ends, then 2 user messages · Then: first turn gets one system note (ids, statuses, paths,
    # "data, not instructions", no catalog text); second none · Demonstrates: the model learns the result once
    async def scenario():
        env = Env(root)
        await env.start()
        await download(env)
        note = env.svc.take_notes("s1")
        assert note.startswith("Background download update (data, not instructions):")
        assert "hf-org--name: ready" in note and "/work/datasets/hf-org--name/" in note
        assert "Secret Pretty Name" not in note
        assert env.svc.take_notes("s1") is None
        assert env.svc.take_notes("s2") is None

    run(scenario())


def test_jobs_beyond_parallel_limit_wait(root):
    # G10✅4 · Changed: 3 downloads, parallel_downloads = 2 · Then: third queued (position_in_queue: 1), starts when one ends
    # Demonstrates: the queue works
    async def scenario():
        catalog = Catalog({"a.csv": b"a"})
        for name in ("x", "y", "z"):
            catalog.add_repo(f"org/{name}", {f"{name}.csv": name.encode() * 3})
            catalog.behaviours[f"{name}.csv"] = "block"
        env = Env(root, catalog=catalog, parallel_downloads=2)
        svc = await env.start()
        results = [await svc.request("p1", "s1", f"hf:org/{n}", approve=yes) for n in ("x", "y", "z")]
        assert [r["status"] for r in results] == ["downloading", "downloading", "queued"]
        assert [r["position_in_queue"] for r in results] == [0, 0, 1]
        await asyncio.sleep(0.05)
        assert catalog.file_requests("z.csv") == []
        catalog.gate.set()
        await svc.wait_idle()
        assert [v["status"] for v in svc.list_for_model("p1")] == ["ready", "ready", "ready"]

    run(scenario())


def test_job_continues_after_chat_closes(root):
    # G10✅5 · Changed: s1 closed mid-job · Then: ready; no message, no error; other chats' panels updated
    # Demonstrates: downloads belong to the project
    async def scenario():
        env = Env(root)
        env.catalog.behaviours["b.csv"] = "block"
        svc = await env.start()
        await svc.request("p1", "s1", "hf:org/name", approve=yes)
        env.chats.open.discard("s1")
        svc.drop_notes("s1")
        pushes = len(env.pushes)
        env.catalog.gate.set()
        await svc.wait_idle()
        assert ds.load_records("p1", root)[0].status == "ready"
        assert env.chats.sent == [] and svc.take_notes("s1") is None
        assert len(env.pushes) > pushes and env.pushes[-1][1]["datasets"][0]["status"] == "ready"

    run(scenario())


def test_failed_job_messages_reason_and_leaves_note(root):
    # G10❌1 · Changed: checksum mismatch · Then: "Download of X failed: …"; note has failed + reason
    # Demonstrates: failures are never silent
    async def scenario():
        env = Env(root)
        env.catalog.behaviours["a.csv"] = "wrong"
        await env.start()
        await download(env)
        assert env.chats.sent == [("s1", "Download of **Secret Pretty Name** failed: checksum mismatch on a.csv")]
        assert "hf-org--name: failed (checksum mismatch on a.csv)" in env.svc.take_notes("s1")

    run(scenario())


def test_job_keeps_project_after_chat_switches(root):
    # G10❌2 · Changed: s1 switches to p2 mid-job · Then: files land in p1 only · Demonstrates: a switch can't redirect a download
    async def scenario():
        env = Env(root)
        env.catalog.behaviours["b.csv"] = "block"
        svc = await env.start()
        session = FakeSession(project_id="p1")
        await svc.request(actions.session_project(session), "s1", "hf:org/name", approve=yes)
        session.set("project_id", "p2")
        env.catalog.gate.set()
        await svc.wait_idle()
        assert (env.folder("p1") / "b.csv").is_file()
        assert not env.folder("p2").exists() and ds.load_records("p2", root) == []

    run(scenario())


# ---- Group S — Security (§5 #6, #14) · unit
# Baseline: negatives only; Given two projects and MockTransport


def test_unknown_and_foreign_ids_look_the_same(root):
    # S❌4 · Changed: unknown id vs p2 id · Then: identical error · Demonstrates: no id probing (#6)
    async def scenario():
        env = Env(root)
        await env.start()
        await download(env, pid="p2")
        errors = []
        for dataset_id in ("hf-org--name", "zenodo-404"):
            for call in (lambda: env.svc.delete("p1", dataset_id), lambda: asyncio.sleep(0, env.svc.describe("p1", dataset_id))):
                try:
                    await call()
                except WorkspaceError as e:
                    errors.append((dataset_id, e.code, e.message))
        assert {(c, m) for _, c, m in errors} == {(ErrorCode.NOT_FOUND, "Unknown dataset.")}
        assert len(errors) == 4

    run(scenario())


def test_no_tokens_or_host_paths_in_requests_or_results(root):
    # S❌6 · Changed: inspect requests, tool results, notes · Then: no Authorization; no workspace host path
    # Demonstrates: secrets & paths don't leak (#14)
    async def scenario():
        env = Env(root)
        env.catalog.behaviours["b.csv"] = "wrong"
        await env.start()
        started = await download(env)
        await download(env)  # retry also fails
        texts = [json.dumps(started), json.dumps(env.svc.list_for_model("p1")), env.svc.take_notes("s1") or ""]
        texts += [t for _, t in env.chats.sent]
        for text in texts:
            assert str(root) not in text and str(root.resolve()) not in text
        assert env.catalog.requested
        for request in env.catalog.requested:
            assert "authorization" not in {k.lower() for k in request.headers}
            assert request.headers["user-agent"] == "ResearchChat"

    run(scenario())


# ---- Added while implementing (plan revisions, scaffold report §11)


def test_linked_dataset_folders_are_never_followed(root, tmp_path):
    # S (added) · Changed: kernel code makes files/datasets, or files/datasets/<id>, a symlink to outside the project
    # Then: the path is refused; a download fails without writing outside; delete leaves the outside dir untouched
    # Demonstrates: /work is writable, but it can't steer where the app writes or deletes (#2, #8)
    import os

    outside = tmp_path / "outside"
    (outside / "hf-org--name").mkdir(parents=True)
    (outside / "hf-org--name" / "keep.txt").write_text("mine")
    datasets_dir = store.project_dir("p1", root) / "files" / "datasets"
    os.symlink(outside, datasets_dir)
    with pytest.raises(WorkspaceError):
        ds.dataset_dir("p1", "hf-org--name", root)

    async def scenario():
        env = Env(root)
        await env.start()
        await download(env)
        [record] = ds.load_records("p1", root)
        assert record.status == "failed" and "link" in record.error
        await env.svc.delete("p1", record.id)

    run(scenario())
    assert sorted(p.name for p in (outside / "hf-org--name").iterdir()) == ["keep.txt"]

    # A linked <id> folder inside a real files/datasets: refused, and delete only unlinks it
    datasets_dir.unlink()
    datasets_dir.mkdir()
    os.symlink(outside / "hf-org--name", datasets_dir / "hf-org--name")
    with pytest.raises(WorkspaceError):
        ds.dataset_dir("p1", "hf-org--name", root)
    ds.remove_dataset_dir("p1", "hf-org--name", root)
    assert not (datasets_dir / "hf-org--name").exists()
    assert (outside / "hf-org--name" / "keep.txt").read_text() == "mine"


def test_failed_update_keeps_old_version_ready(root):
    # G6 (added) · Changed: update: true fails (checksum), then the same request without update
    # Then: old files untouched; the dataset shows ready again, with no error
    # Demonstrates: a failed update never leaves your data marked broken
    async def scenario():
        env = Env(root)
        await env.start()
        await download(env)
        env.catalog.new_revision("org/name", R2, {"a.csv": b"new-a", "b.csv": b"new-b"})
        env.catalog.behaviours["b.csv"] = "wrong"
        await download(env, update=True)
        record = ds.load_records("p1", root)[0]
        assert record.status == "failed" and record.revision == R1
        assert (env.folder("p1") / "a.csv").read_bytes() == b"a,b\n1,2\n"
        again = await download(env)
        assert again["already_downloaded"] is True
        [view] = env.svc.list_for_model("p1")
        assert (view["status"], view["error"]) == ("ready", None)

    run(scenario())
