"""Tests for the shared dataset pool and its index in the database.

Same fakes as test_dataset_service.py (no network, fake disk, tmp_path), reused from there.
"""

import asyncio
import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from researchchat.db.engine import database_for
from researchchat.workspace import WorkspaceError, store
from researchchat.workspace.datasets import pool as dataset_pool
from researchchat.workspace.datasets import sources as src
from researchchat.workspace.datasets import store as ds
from researchchat.workspace.datasets.pool import DatasetPool, PoolEntry, PoolFile
from researchchat.workspace.kernels import KernelRegistry
from tests.conftest import fake_lookup
from tests.datasets.test_dataset_service import (
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


# ---- Shared pool · unit + 1 docker
# Baseline: Given project p1 has dataset X ready in the pool · When project p2 requests X


async def pooled_for_p1(root, catalog=None, files=None):
    env = Env(root, catalog=catalog)
    await env.start()
    await download(env, files)
    return env


def test_second_project_links_pool_files_without_download(root):
    # Changed: —
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
    # Changed: p2 asks ["*.csv", "*.json"], pool has only csv
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
    # Changed: p1 and p2 request X (not pooled) at once
    # Then: one job; each file fetched once; both ready
    # Demonstrates: no duplicate downloads
    async def scenario():
        env = Env(root)
        env.catalog.behaviours["a.csv"] = "block"
        svc = await env.start()
        await asyncio.gather(
            svc.request("p1", "s1", "hf:org/name", approve=yes), svc.request("p2", "s2", "hf:org/name", approve=yes),
        )
        assert len(svc.active_jobs()) == 1
        env.catalog.gate.set()
        await svc.wait_idle()
        assert len(env.catalog.file_requests("a.csv")) == 1 and len(env.catalog.file_requests("b.csv")) == 1
        assert [svc.list_for_model(p)[0]["status"] for p in ("p1", "p2")] == ["ready", "ready"]
        assert {s for s, _ in env.chats.sent} == {"s1", "s2"}

    run(scenario())


def test_older_pooled_revision_is_reused_without_update(root):
    # Changed: pool has r1, catalog at r2, p2 asks without update
    # Then: p2 linked to r1; no catalog call; with update: true a new entry r2 is made and only p2 switches
    # Demonstrates: no silent version changes across projects
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
    # Changed: pooled file's size or mtime_ns differs
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
    # Changed: crafted entry id / path
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
    # Changed: in the kernel, write to /work/datasets/<id>/a.csv, and delete it through the pool mount
    # Then: both fail (read-only file system); pool file unchanged. Removing the link itself only makes
    # the dataset missing in this project
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


def test_cleanup_waits_for_a_project_linking_at_the_same_time(root):
    # Changed: p1 deletes its last use while p2 links the same entry
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


# ---- Pool index in the database · integration
# Baseline: Given a workspace at head · When `pool.add_entry(entry)`; `pool.save_index()`; a new `DatasetPool(root).entries()`

MTIME_NS = 1794468807764441482  # a real value from the workspace's pool index


def pool_entry(slug=ENTRY_R1, created_at="2026-11-15T00:00:00+00:00", files=None):
    return PoolEntry(
        slug, "huggingface", "org/name", R1, "org/name", "https://huggingface.co/datasets/org/name", "mit",
        files if files is not None else [PoolFile("b.csv", 5, "sha256:" + "0" * 64, True, MTIME_NS),
                                         PoolFile("a.csv", 3, None, False, None)],
        created_at,
    )


def saved_pool(root, *entries) -> DatasetPool:
    pool = DatasetPool(root)
    for entry in entries or (pool_entry(),):
        pool.add_entry(entry)
    pool.save_index()
    return pool


def use_entry(root, project_id, entry_id=ENTRY_R1):
    ds.save_project_datasets(project_id, [ds.ProjectDataset("hf-org--name", entry_id, None, "ready", ["b.csv"])], root)


def entry_pk(root, slug=ENTRY_R1):
    with database_for(root).connect() as connection:
        return connection.execute(text("SELECT pk FROM pool_entries WHERE slug = :slug"), {"slug": slug}).scalar()


def test_pool_entries_round_trip_with_files_in_order(root):
    # baseline
    # Changed: —
    # Then: equal PoolEntry with files in the same order
    # Demonstrates: the index survives a restart
    saved_pool(root)

    assert list(DatasetPool(root).entries().values()) == [pool_entry()]


def test_large_mtime_ns_round_trips(root):
    # edge
    # Changed: mtime_ns=1794468807764441482
    # Then: the same int
    # Demonstrates: change detection still works
    saved_pool(root)

    assert DatasetPool(root).get_entry(ENTRY_R1).file("b.csv").mtime_ns == MTIME_NS


def test_projects_using_reads_from_database(root):
    # edge
    # Changed: entry used by p1 and p2, not p3
    # Then: ["p1", "p2"]
    # Demonstrates: "used by" counts come from one query
    store.create_project("P3", root, project_id="p3")
    pool = saved_pool(root)
    use_entry(root, "p2")
    use_entry(root, "p1")

    assert pool.projects_using(ENTRY_R1) == ["p1", "p2"]


def test_find_entries_newest_first(root):
    # edge
    # Changed: two revisions of one dataset
    # Then: newest created_at first
    # Demonstrates: reuse picks the same version as today
    older = pool_entry(ENTRY_R1, "2026-11-01T00:00:00+00:00")
    newer = pool_entry(f"hf-org--name@{R2[:7]}", "2026-11-10T00:00:00+00:00")
    saved_pool(root, older, newer)

    found = DatasetPool(root).find_entries("huggingface", "org/name")

    assert [e.id for e in found] == [newer.id, older.id]


def test_saving_the_index_again_keeps_entry_keys(root):
    # edge
    # Changed: entry used by p1; change its files; save_index() again
    # Then: same pool_entries.pk; p1's row still points to it; files replaced
    # Demonstrates: an upsert on slug never breaks a project's reference
    pool = saved_pool(root)
    use_entry(root, "p1")
    first_pk = entry_pk(root)

    pool.get_entry(ENTRY_R1).files = [PoolFile("c.csv", 7, None, True, 1)]
    pool.save_index()

    assert entry_pk(root) == first_pk
    assert pool.projects_using(ENTRY_R1) == ["p1"]
    assert [f.path for f in DatasetPool(root).get_entry(ENTRY_R1).files] == ["c.csv"]


def test_entry_in_use_cannot_be_deleted(root):
    # negative
    # Changed: delete the entry row while p1 uses it
    # Then: IntegrityError; entry and files still there
    # Demonstrates: cleanup can never orphan a project
    pool = saved_pool(root)
    use_entry(root, "p1")

    with pytest.raises(IntegrityError):
        pool.save_index([])

    assert list(DatasetPool(root).entries()) == [ENTRY_R1]
    assert len(DatasetPool(root).get_entry(ENTRY_R1).files) == 2


def test_tampered_pool_row_is_skipped(root, caplog):
    # replaces test_corrupt_pool_index_is_rebuilt
    # Changed: rows with entry slug ../x and file path ../../etc/passwd
    # Then: skipped with a warning; good entries returned
    # Demonstrates: a tampered row can't make a link target outside the pool
    saved_pool(root, pool_entry(), pool_entry("zenodo-1", files=[PoolFile("ok.csv", 1, None, True)]))
    with database_for(root).begin() as connection:
        connection.execute(text("INSERT INTO pool_entries (slug, source, source_id, name) VALUES ('../x', 'zenodo', '1', 'x')"))
        connection.execute(text("UPDATE pool_files SET path = '../../etc/passwd' WHERE path = 'ok.csv'"))

    assert list(DatasetPool(root).entries()) == [ENTRY_R1]
    assert caplog.text.count("Ignored a pool entry row") == 2


def test_failed_index_save_keeps_previous_index(root, monkeypatch):
    # negative
    # Changed: an insert raises mid-save
    # Then: previous entries and files unchanged
    # Demonstrates: the index is all-or-nothing
    pool = saved_pool(root)
    pool.add_entry(pool_entry("zenodo-2", files=[PoolFile("z.csv", 1, None, True)]))
    real_replace = dataset_pool._replace_entry_files

    def fail_for_new_entry(connection, pk, files):
        if files and files[0].path == "z.csv":
            raise OSError("disk full")
        real_replace(connection, pk, files)

    monkeypatch.setattr(dataset_pool, "_replace_entry_files", fail_for_new_entry)

    with pytest.raises(OSError, match="disk full"):
        pool.save_index()

    assert list(DatasetPool(root).entries().values()) == [pool_entry()]


def test_duplicate_pool_slug_is_refused_by_the_database(root):
    # negative
    # Changed: insert a second row with an existing entry slug directly
    # Then: IntegrityError (UNIQUE); one row
    # Demonstrates: one folder is never two entries
    saved_pool(root)

    with pytest.raises(IntegrityError), database_for(root).begin() as connection:
        connection.execute(text(
            "INSERT INTO pool_entries (slug, source, source_id, name) VALUES (:slug, 'zenodo', '1', 'x')"
        ), {"slug": ENTRY_R1})

    with database_for(root).connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM pool_entries")).scalar() == 1
