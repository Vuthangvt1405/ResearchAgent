"""Tests for the shared dataset pool and the NB-3 migration (NB-4 plan §7: G11, G14).

Same fakes as test_dataset_service.py (no network, fake disk, tmp_path), reused from there.
"""

import asyncio
import hashlib
import json
import os

import pytest

from researchchat.workspace import WorkspaceError, store
from researchchat.workspace import dataset_sources as src
from researchchat.workspace import datasets_store as ds
from researchchat.workspace.dataset_pool import DatasetPool
from researchchat.workspace.kernels import KernelRegistry
from tests.conftest import fake_lookup
from tests.test_dataset_service import (
    R1,
    R2,
    Catalog,
    Env,
    download,
    records,
    run,
    until,
    yes,
)

A_CSV = b"a,b\n1,2\n"
ENTRY_R1 = f"hf-org--name@{R1[:7]}"


@pytest.fixture(autouse=True)
def no_dns(monkeypatch):
    monkeypatch.setattr(src, "lookup_host", fake_lookup)


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "ws"
    store.create_project("P1", root, project_id="p1")
    store.create_project("P2", root, project_id="p2")
    return root


# ---- Group 11: Shared pool (AC15–AC18, AC30, SEC9, SEC12, SEC16, SEC23) · unit + 1 docker
# Baseline: Given project p1 has dataset X ready in the pool · When project p2 requests X


async def pooled_for_p1(root, catalog=None, files=None):
    env = Env(root, catalog=catalog)
    await env.start()
    await download(env, files)
    return env


def test_second_project_links_pool_files_without_download(root):
    # G11✅1 · Changed: —
    # Then: p2 gets links into the pool + record ready, from_pool: true; no HTTP request
    # Demonstrates: the pool saves the download
    async def scenario():
        env = await pooled_for_p1(root)
        before = len(env.catalog.requested)
        started = await download(env, pid="p2", session="s2")
        assert (started["status"], started["from_pool"]) == ("ready", True)
        assert env.catalog.requested[before:] == []
        link = env.folder("p2") / "a.csv"
        assert link.is_symlink() and os.readlink(link) == DatasetPool.link_target(ENTRY_R1, "a.csv")
        assert link.read_bytes() == A_CSV
        assert records(root, "p2")[0].status == "ready" and records(root, "p2")[0].pool_entry == ENTRY_R1

    run(scenario())


def test_second_project_downloads_only_files_pool_lacks(root):
    # G11✅2 · Changed: p2 asks ["*.csv", "*.json"], pool has only csv
    # Then: job fetches only json; p2 sees both; p1 still sees only csv
    # Demonstrates: each project sees what it asked for
    async def scenario():
        catalog = Catalog({"a.csv": A_CSV, "meta.json": b"{}"})
        env = await pooled_for_p1(root, catalog, ["*.csv"])
        before = len(catalog.file_requests())
        started = await download(env, ["*.csv", "*.json"], pid="p2", session="s2")
        assert started["download_bytes"] == len(b"{}")
        assert [r.url.path.rsplit("/", 1)[1] for r in catalog.file_requests()[before:]] == ["meta.json"]
        assert sorted(p.name for p in env.folder("p2").iterdir()) == ["a.csv", "meta.json"]
        assert sorted(p.name for p in env.folder("p1").iterdir()) == ["a.csv"]
        assert env.svc.list_for_model("p2")[0]["status"] == "ready"

    run(scenario())


def test_two_projects_requesting_same_files_share_one_job(root):
    # G11✅3 · Changed: p1 and p2 request X (not pooled) at once
    # Then: one job; each file fetched once; both ready
    # Demonstrates: no duplicate downloads
    async def scenario():
        env = Env(root)
        env.catalog.behaviours["a.csv"] = "block"
        svc = await env.start()
        await asyncio.gather(
            svc.request("p1", "s1", "hf:org/name", approve=yes), svc.request("p2", "s2", "hf:org/name", approve=yes),
        )
        assert len(svc._jobs) == 1
        env.catalog.gate.set()
        await svc.wait_idle()
        assert len(env.catalog.file_requests("a.csv")) == 1 and len(env.catalog.file_requests("b.csv")) == 1
        assert [svc.list_for_model(p)[0]["status"] for p in ("p1", "p2")] == ["ready", "ready"]
        assert {s for s, _ in env.chats.sent} == {"s1", "s2"}

    run(scenario())


def test_older_pooled_revision_is_reused_without_update(root):
    # G11✅5 · Changed: pool has r1, catalog at r2, p2 asks without update
    # Then: p2 linked to r1; no catalog call; with update: true a new entry r2 is made and only p2 switches
    # Demonstrates: no silent version changes across projects (AC30)
    async def scenario():
        env = await pooled_for_p1(root)
        env.catalog.new_revision("org/name", R2, {"a.csv": b"new-a", "b.csv": b"new-b"})
        before = len(env.catalog.requested)
        await download(env, pid="p2", session="s2")
        assert env.catalog.requested[before:] == []
        assert records(root, "p2")[0].revision == R1

        await download(env, update=True, pid="p2", session="s2")
        assert records(root, "p2")[0].revision == R2 and records(root, "p1")[0].revision == R1
        assert (env.folder("p2") / "a.csv").read_bytes() == b"new-a"
        assert (env.folder("p1") / "a.csv").read_bytes() == A_CSV
        assert sorted(e.revision for e in DatasetPool(root).load_index()) == [R1, R2]

    run(scenario())


def test_changed_pool_file_is_rechecked_before_linking(root):
    # G11❌1 · Changed: pooled file's size or mtime_ns differs
    # Then: checksum re-checked; bad file downloaded again before p2 is linked
    # Demonstrates: changed data is never reused blindly
    async def scenario():
        env = await pooled_for_p1(root)
        pooled = env.pool_file("a.csv")
        pooled.chmod(0o644)
        pooled.write_bytes(b"X" * len(A_CSV))  # same size, new mtime, wrong bytes
        before = len(env.catalog.file_requests("a.csv"))
        await download(env, pid="p2", session="s2")
        assert len(env.catalog.file_requests("a.csv")) == before + 1
        assert (env.folder("p2") / "a.csv").read_bytes() == A_CSV

        os.utime(pooled, ns=(1, 1))  # only mtime changes; bytes still right → kept, not fetched
        before = len(env.catalog.file_requests("a.csv"))
        await download(env, pid="p2", session="s2")
        assert len(env.catalog.file_requests("a.csv")) == before

    run(scenario())


def test_links_never_point_outside_pool(root):
    # G11❌2 · Changed: crafted entry id / path
    # Then: refused; no symlink created
    # Demonstrates: links can't expose host files
    pool = DatasetPool(root)
    for bad_entry in ("../p1", "a/b", "", "UPPER", "x@" + "y" * 20, "/etc", None):
        with pytest.raises(WorkspaceError):
            pool.link_target(bad_entry, "a.csv")
        with pytest.raises(WorkspaceError):
            pool.entry_dir(bad_entry)
    for bad_path in ("../x", "a/../../x", "/etc/passwd", "a\\b", ""):
        with pytest.raises(WorkspaceError):
            pool.link_target(ENTRY_R1, bad_path)
        with pytest.raises(WorkspaceError):
            pool.pool_file_path(ENTRY_R1, bad_path)
    assert pool.link_target(ENTRY_R1, "data/train.csv") == f"../../../../../.dataset-pool/{ENTRY_R1}/data/train.csv"

    # A folder on the way that kernel code swapped for a link is never written through
    elsewhere = root.parent / "elsewhere"
    elsewhere.mkdir()
    folder = ds.dataset_dir("p1", "hf-org--name", root)
    folder.mkdir(parents=True)
    (folder / "data").symlink_to(elsewhere)
    with pytest.raises(WorkspaceError):
        ds.link_path("p1", "hf-org--name", "data/train.csv", root)
    assert list(elsewhere.iterdir()) == []


@pytest.mark.docker
def test_kernel_cannot_write_pooled_files(root):
    # G11❌3 · Changed: in the kernel, write to /work/datasets/<id>/a.csv, and delete it through the pool mount
    # Then: both fail (read-only file system); pool file unchanged. Removing the link itself only makes
    # the dataset missing in this project (AC18)
    # Demonstrates: one project can't corrupt another's data
    async def scenario():
        env = await pooled_for_p1(root)
        kernels = KernelRegistry(root=root)
        files_dir = store.project_dir("p1", root) / store.FILES_DIR
        code = (
            "import os\nr = []\n"
            "for act in (lambda: open('/work/datasets/hf-org--name/a.csv', 'w'),"
            f" lambda: os.remove('/.dataset-pool/{ENTRY_R1}/a.csv')):\n"
            "    try:\n        act(); r.append('ok')\n    except OSError as e:\n        r.append(e.errno)\n"
            "print(open('/work/datasets/hf-org--name/a.csv').read() == 'a,b\\n1,2\\n', r)"
        )
        try:
            result = await kernels.execute("p1", code, _ignore, files_dir=files_dir)
            text = "".join(o.get("text", "") for o in result.outputs)
            assert text.startswith("True [30, 30]"), text  # EROFS
        finally:
            await kernels.stop_all()
        assert env.pool_file("a.csv").read_bytes() == A_CSV

    run(scenario())


async def _ignore(_output):
    return None


def test_corrupt_pool_index_is_rebuilt(root):
    # G11❌4 · Changed: .dataset-pool.json invalid
    # Then: rebuilt from the pool folders; .bad copy kept; nothing deleted; the projects' links keep working
    # Demonstrates: a broken index never loses data
    async def scenario():
        env = await pooled_for_p1(root)
        index = root / ".dataset-pool.json"
        index.write_text("{not json", encoding="utf-8")
        env2 = Env(root, catalog=env.catalog)
        await env2.start()
        assert (root / ".dataset-pool.json.bad").read_text(encoding="utf-8") == "{not json"
        [entry] = DatasetPool(root).load_index()
        assert entry.id == ENTRY_R1 and entry.ready_paths() == {"a.csv", "b.csv"}
        assert env2.svc.list_for_model("p1")[0]["status"] == "ready"
        assert (env2.folder("p1") / "a.csv").read_bytes() == A_CSV

    run(scenario())


def test_cleanup_waits_for_a_project_linking_at_the_same_time(root):
    # G11❌5 · Changed: p1 deletes its last use while p2 links the same entry
    # Then: entry kept, p2 linked
    # Demonstrates: cleanup can't delete data someone just started using
    async def scenario():
        env = await pooled_for_p1(root)
        before = len(env.catalog.file_requests())
        release_push = asyncio.Event()
        plain_notify = env.svc.notify

        async def slow_notify(pid, props):
            if pid == "p2":
                await release_push.wait()  # p2's request is still inside the pool lock here
            await plain_notify(pid, props)

        env.svc.notify = slow_notify
        linking = asyncio.create_task(env.svc.request("p2", "s2", "hf:org/name", approve=yes))
        await until(env.svc.pool.lock.locked)
        deleting = asyncio.create_task(env.svc.delete("p1", "hf-org--name"))
        await asyncio.sleep(0.02)
        assert not deleting.done()  # cleanup waits for the lock
        release_push.set()
        await linking
        result = await deleting
        assert (result["freed_bytes"], result["still_used_by"]) == (0, 1)
        assert env.catalog.file_requests()[before:] == []
        assert env.pool_file("a.csv").read_bytes() == A_CSV
        assert (env.folder("p2") / "a.csv").read_bytes() == A_CSV
        assert env.svc.list_for_model("p2")[0]["status"] == "ready"

    run(scenario())


# ---- Group 14: Migration from NB-3 (AC29, SEC24) · unit
# Baseline: Given projects with NB-3 datasets.json format 1 and real files in files/datasets/<id>/
#           · When migrate() runs on start


def nb3_dataset(root, pid, files=None, revision=R1):
    """Write a format 1 record and its real files, the way NB-3 left them."""
    files = files or {"a.csv": A_CSV, "b.csv": b"x\n" * 50}
    folder = ds.dataset_dir(pid, "hf-org--name", root)
    folder.mkdir(parents=True, exist_ok=True)
    for path, body in files.items():
        (folder / path).write_bytes(body)
    record = ds.DatasetRecord(
        id="hf-org--name", name="org/name", source="huggingface", source_id="org/name", revision=revision,
        url="https://huggingface.co/datasets/org/name", license="mit", selection=None, status="ready",
        files=[ds.DatasetFile(p, len(b), "sha256:" + hashlib.sha256(b).hexdigest(), True) for p, b in files.items()],
        requested_at="2026-11-01T00:00:00+00:00", downloaded_at="2026-11-01T00:01:00+00:00",
    )
    ds.save_records(pid, [record], root)
    return folder


def test_migration_moves_files_into_pool_and_links_them(root):
    # G14✅1 · Changed: one project, one dataset
    # Then: files in .dataset-pool/<entry>/; links in files/datasets/<id>/; format 2 + .v1 backup; same /work paths
    # Demonstrates: old downloads keep working
    folder = nb3_dataset(root, "p1")
    report = DatasetPool(root).migrate()
    assert report.migrated_projects == ["p1"]
    pool = DatasetPool(root)
    assert pool.pool_file_path(ENTRY_R1, "a.csv").read_bytes() == A_CSV
    assert (folder / "a.csv").is_symlink() and (folder / "a.csv").read_bytes() == A_CSV
    assert json.loads(ds.manifest_path("p1", root).read_text())["format"] == 2
    assert json.loads((ds.manifest_path("p1", root).with_name("datasets.json.v1")).read_text())["format"] == 1

    async def scenario():
        env = Env(root)
        await env.start()
        [view] = env.svc.list_for_model("p1")
        assert view["status"] == "ready" and view["path"] == "/work/datasets/hf-org--name"
        assert view["name"] == "org/name" and view["license"] == "mit"

    run(scenario())


def test_same_dataset_in_two_projects_is_stored_once(root):
    # G14✅2 · Changed: p1 and p2 both have X at the same revision
    # Then: one pool entry; p2's duplicate files removed; both linked
    # Demonstrates: migration frees duplicate space
    nb3_dataset(root, "p1")
    p2_folder = nb3_dataset(root, "p2")
    DatasetPool(root).migrate()
    [entry] = DatasetPool(root).load_index()
    assert entry.id == ENTRY_R1
    assert all((p2_folder / p).is_symlink() for p in ("a.csv", "b.csv"))
    assert (p2_folder / "a.csv").read_bytes() == A_CSV
    assert sorted(p.name for p in DatasetPool(root).entry_dir(ENTRY_R1).iterdir()) == ["a.csv", "b.csv"]


def test_migration_is_safe_to_run_twice(root):
    # G14✅3 · Changed: run migrate() again
    # Then: no changes, no errors
    # Demonstrates: restarts don't redo or break anything
    nb3_dataset(root, "p1")
    DatasetPool(root).migrate()
    manifest = ds.manifest_path("p1", root).read_text()
    index = (root / ".dataset-pool.json").read_text()
    report = DatasetPool(root).migrate()
    assert report.migrated_projects == [] and report.skipped_projects == []
    assert ds.manifest_path("p1", root).read_text() == manifest
    assert (root / ".dataset-pool.json").read_text() == index


def test_migration_marks_gone_or_changed_files(root):
    # G14❌1 · Changed: one file deleted, one with a different size
    # Then: deleted → missing; changed → not moved, left in place, not ready in the pool
    # Demonstrates: migration never puts wrong data in the pool
    folder = nb3_dataset(root, "p1", {"a.csv": A_CSV, "b.csv": b"bb", "c.csv": b"cc"})
    (folder / "b.csv").unlink()
    (folder / "c.csv").write_bytes(b"changed!")
    DatasetPool(root).migrate()
    [entry] = DatasetPool(root).load_index()
    assert entry.ready_paths() == {"a.csv"}
    assert (folder / "c.csv").read_bytes() == b"changed!" and not (folder / "c.csv").is_symlink()
    assert not DatasetPool(root).pool_file_path(ENTRY_R1, "c.csv").exists()

    async def scenario():
        env = Env(root)
        await env.start()
        [view] = env.svc.list_for_model("p1")
        assert view["status"] == "missing" and sorted(view["missing_files"]) == ["b.csv", "c.csv"]

    run(scenario())


def test_migration_resumes_after_a_crash(root):
    # G14❌2 · Changed: crash after project 1 of 2
    # Then: next start migrates project 2 only; project 1 untouched
    # Demonstrates: an interrupted migration finishes cleanly
    nb3_dataset(root, "p1")
    DatasetPool(root).migrate_project("p1")  # the first run got this far
    p1_manifest = ds.manifest_path("p1", root).read_text()
    nb3_dataset(root, "p2")
    report = DatasetPool(root).migrate()
    assert report.migrated_projects == ["p2"]
    assert ds.manifest_path("p1", root).read_text() == p1_manifest
    assert (ds.dataset_dir("p2", "hf-org--name", root) / "a.csv").is_symlink()


def test_migration_skips_corrupt_manifest(root):
    # G14❌3 · Changed: p2/datasets.json invalid
    # Then: p2 skipped and logged (A6 rule); p1 migrated
    # Demonstrates: one broken project doesn't block the rest
    nb3_dataset(root, "p1")
    ds.manifest_path("p2", root).write_text("{not json", encoding="utf-8")
    report = DatasetPool(root).migrate()
    assert report.migrated_projects == ["p1"] and report.skipped_projects == ["p2"]
    assert ds.manifest_path("p2", root).read_text() == "{not json"


def test_migration_resumes_after_a_crash_inside_a_project(root):
    # G14❌4 (added in implementation) · Changed: crash after a file was moved but before datasets.json
    # was rewritten, and the pool index is gone too
    # Then: the next start finds the moved file, links it, and keeps the catalog details; nothing lost
    # Demonstrates: a crash at any point of the move loses no data
    folder = nb3_dataset(root, "p1")
    pool = DatasetPool(root)
    target = pool.pool_file_path(ENTRY_R1, "a.csv")
    target.parent.mkdir(parents=True)
    os.rename(folder / "a.csv", target)  # the first run got this far
    report = DatasetPool(root).migrate()
    assert report.migrated_projects == ["p1"]
    [entry] = DatasetPool(root).load_index()
    assert (entry.id, entry.source_id) == (ENTRY_R1, "org/name")
    assert entry.ready_paths() == {"a.csv", "b.csv"}
    assert (folder / "a.csv").is_symlink() and (folder / "a.csv").read_bytes() == A_CSV


def test_project_skipped_by_migration_is_never_overwritten(root):
    # G14❌5 (added in implementation) · Changed: the start-up migration failed for p1 (stays format 1)
    # Then: it's migrated when first read; the NB-3 data is linked, .v1 kept, nothing downloaded again
    # Demonstrates: an un-migrated project is never read as empty and overwritten
    nb3_dataset(root, "p1")

    async def scenario():
        env = Env(root)
        broken = env.start
        original = DatasetPool.migrate
        DatasetPool.migrate = lambda self: (_ for _ in ()).throw(OSError("disk hiccup"))
        try:
            await broken()
        finally:
            DatasetPool.migrate = original
        # migrated when start-up first read the project, instead of being read as empty
        assert json.loads(ds.manifest_path("p1", root).read_text())["format"] == 2
        before = len(env.catalog.file_requests())
        started = await download(env)
        assert started["already_downloaded"] is True
        assert env.catalog.file_requests()[before:] == []
        assert ds.manifest_path("p1", root).with_name("datasets.json.v1").is_file()
        assert (env.folder("p1") / "a.csv").read_bytes() == A_CSV

    run(scenario())
