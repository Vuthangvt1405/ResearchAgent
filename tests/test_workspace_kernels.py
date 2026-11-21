"""Running code in the Docker kernel (needs Docker).
These start real kernel containers; they skip when Docker or the image is missing.
"""

import asyncio
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from sillytherin.workspace import ErrorCode, WorkspaceError, kernels, store
from sillytherin.workspace.datasets import store as ds
from sillytherin.workspace.datasets.pool import POOL_DIR, DatasetPool
from sillytherin.workspace.datasets.views import VIEWS_DIR, ProjectViews, ViewFile
from sillytherin.workspace.kernels import (
    SCOPE_LABEL,
    ContainerMounts,
    DockerSettings,
    KernelRegistry,
    _docker,
)
from sillytherin.workspace.service import NotebookService, output_props

pytestmark = pytest.mark.docker


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def root(tmp_path):
    return tmp_path / "workspaces"


def make_registry(root, **kwargs):
    kwargs.setdefault("timeout_seconds", 20)
    return KernelRegistry(root=root, **kwargs)


async def noop(out):
    pass


def files(root, pid):
    return store.project_dir(pid, root) / "files"


async def exec_(reg, root, pid, code):
    return await reg.execute(pid, code, noop, files(root, pid))


def texts(result):
    return [output_props(o) for o in result.outputs]


def kernel_test(fn):
    """Run an async scenario with a fresh registry and project P; always stop the kernels."""

    def wrapper(root, **kw):
        pid = store.create_project("P", root).id
        reg = make_registry(root)

        async def scenario():
            try:
                await fn(reg, root, pid, **kw)
            finally:
                await reg.stop_all()

        run(scenario())

    wrapper.__name__ = fn.__name__
    return wrapper


# ---- Running code · integration (kernel)
# Baseline: Given project P with a running kernel · When a cell is executed


def test_run_shows_last_value_and_execution_count(root):
    # Demonstrates: basic Jupyter behaviour
    @kernel_test
    async def go(reg, root, pid):
        result = await exec_(reg, root, pid, "1+1")
        assert result.status == "done" and result.execution_count == 1
        assert texts(result) == [{"kind": "result", "text": "2", "image": ""}]

    go(root)


def test_print_goes_to_stdout_output(root):
    @kernel_test
    async def go(reg, root, pid):
        result = await exec_(reg, root, pid, 'print("hi")')
        assert texts(result) == [{"kind": "stdout", "text": "hi\n", "image": ""}]

    go(root)


def test_variables_persist_between_cells(root):
    # Demonstrates: one session per project
    @kernel_test
    async def go(reg, root, pid):
        await exec_(reg, root, pid, "x = 5")
        result = await exec_(reg, root, pid, "x * 2")
        assert texts(result)[0]["text"] == "10" and result.execution_count == 2

    go(root)


def test_matplotlib_chart_becomes_png_output(root):
    # Demonstrates: charts work
    @kernel_test
    async def go(reg, root, pid):
        result = await exec_(reg, root, pid, "import matplotlib.pyplot as plt\nplt.plot([1, 3, 2])\nplt.show()")
        images = [o for o in texts(result) if o["kind"] == "image"]
        assert result.status == "done" and len(images) == 1
        assert images[0]["image"].startswith("iVBOR")  # base64 PNG

    go(root)


def test_relative_paths_use_project_files_dir(root):
    @kernel_test
    async def go(reg, root, pid):
        await exec_(reg, root, pid, 'open("a.txt", "w").write("hello")')
        assert (files(root, pid) / "a.txt").read_text() == "hello"

    go(root)


def service_with_cells(root, sources):
    """A service on real kernels and project P with these cells ("# note" = markdown)."""
    pid = store.create_project("P", root).id
    nb = store.load_notebook(pid, root)
    ids = []
    for src in sources:
        cell = store.add_cell(nb, "markdown" if src.startswith("# note") else "code", None)
        cell.source = src
        ids.append(cell.id)
    store.save_notebook(pid, nb, root)
    reg = make_registry(root)
    pushes = []

    async def notify(project_id, props):
        pushes.append(props)

    return NotebookService(reg, root=root, notify=notify), reg, pid, ids, pushes


def test_run_all_stops_at_first_error(root):
    # Demonstrates: Jupyter's run-all behaviour
    svc, reg, pid, ids, _ = service_with_cells(root, ["a = 1", "1/0", "c = 3"])

    async def go():
        try:
            props = await svc.run_all(pid, 0)
            status = [c["status"] for c in props["cells"]]
            assert status == ["done", "error", "idle"]
        finally:
            await reg.stop_all()

    run(go())


def test_run_all_skips_notes(root):
    svc, reg, pid, ids, _ = service_with_cells(root, ["a = 1", "# note: why", "a + 1"])

    async def go():
        try:
            props = await svc.run_all(pid, 0)
            cells = props["cells"]
            assert [c["execution_count"] for c in cells] == [1, None, 2]
            assert cells[1]["source"] == "# note: why" and cells[1]["outputs"] == []
        finally:
            await reg.stop_all()

    run(go())


def test_long_line_output_is_not_wrapped(root):
    # Demonstrates: the panel can scroll it sideways
    @kernel_test
    async def go(reg, root, pid):
        result = await exec_(reg, root, pid, 'print("x" * 2000)')
        assert texts(result)[0]["text"] == "x" * 2000 + "\n"

    go(root)


def test_exception_shows_traceback_and_error_status(root):
    # Demonstrates: errors don't kill the session
    @kernel_test
    async def go(reg, root, pid):
        result = await exec_(reg, root, pid, "1/0")
        out = texts(result)
        assert result.status == "error" and out[0]["kind"] == "error"
        assert "ZeroDivisionError" in out[0]["text"] and "\x1b[" not in out[0]["text"]
        assert texts(await exec_(reg, root, pid, "1+1"))[0]["text"] == "2"

    go(root)


def test_long_output_is_truncated(root):
    pid = store.create_project("P", root).id
    reg = make_registry(root, max_output_chars=5000)

    async def go():
        try:
            result = await exec_(reg, root, pid, 'for i in range(20000): print("line", i)')
            text = "".join(o["text"] for o in texts(result))
            assert len(text) <= 5000 + 40 and text.endswith("[output truncated]\n")
        finally:
            await reg.stop_all()

    run(go())


def test_html_output_is_returned_as_text(root):
    @kernel_test
    async def go(reg, root, pid):
        result = await exec_(reg, root, pid, 'from IPython.display import HTML, display\ndisplay(HTML("<script>alert(1)</script>"))')
        out = texts(result)
        assert all(o["kind"] in ("stdout", "stderr", "result", "image", "error") for o in out)
        assert out[0]["kind"] == "result" and "<IPython.core.display.HTML object>" in out[0]["text"]

    go(root)


def test_broken_kernel_channel_is_reported_at_once(root):
    @kernel_test
    async def go(reg, root, pid):
        await exec_(reg, root, pid, "x = 1")

        async def broken_channel(*args, **kwargs):
            raise RuntimeError("channel closed")

        reg._kernels[pid].client.get_iopub_msg = broken_channel
        started = time.monotonic()
        with pytest.raises(WorkspaceError) as err:
            await exec_(reg, root, pid, "x")
        assert err.value.code == ErrorCode.KERNEL_DEAD and reg.status(pid) == "dead"
        assert time.monotonic() - started < reg.timeout_seconds

    go(root)


def test_dead_kernel_is_reported_and_restartable(root):
    @kernel_test
    async def go(reg, root, pid):
        await exec_(reg, root, pid, "x = 1")
        await asyncio.to_thread(_docker, "kill", reg.container_name(pid))
        with pytest.raises(WorkspaceError) as err:
            await exec_(reg, root, pid, "x")
        assert err.value.code == ErrorCode.KERNEL_DEAD and reg.status(pid) == "dead"
        await reg.restart(pid, files(root, pid))
        assert texts(await exec_(reg, root, pid, "2+2"))[0]["text"] == "4"

    go(root)


# ---- Interrupt, timeout, restart · integration (kernel)
# Baseline: Given `x = 1` ran in P · When a long cell `while True: pass` runs


def test_interrupt_stops_run_and_keeps_variables(root):
    # Demonstrates: Stop doesn't lose work
    @kernel_test
    async def go(reg, root, pid):
        await exec_(reg, root, pid, "x = 1")
        task = asyncio.create_task(exec_(reg, root, pid, "while True: pass"))
        await asyncio.sleep(1.5)
        await reg.interrupt(pid)
        result = await task
        assert result.status == "interrupted"
        assert texts(await exec_(reg, root, pid, "x"))[0]["text"] == "1"

    go(root)


def test_timeout_interrupts_long_cell(root):
    # Demonstrates: runaway code is stopped
    pid = store.create_project("P", root).id
    reg = make_registry(root, timeout_seconds=2)

    async def go():
        try:
            await exec_(reg, root, pid, "x = 1")
            result = await exec_(reg, root, pid, "while True: pass")
            assert result.status == "timeout" and reg.status(pid) == "idle"
            assert "Timed out" in texts(result)[-1]["text"]
        finally:
            await reg.stop_all()

    run(go())


def test_restart_clears_variables_keeps_cells(root):
    svc, reg, pid, ids, _ = service_with_cells(root, ["x = 1", "x"])

    async def go():
        try:
            await svc.run_all(pid, 0)
            props = await svc.restart(pid)
            assert [c["source"] for c in props["cells"]] == ["x = 1", "x"]
            result = await exec_(reg, root, pid, "x")
            assert result.status == "error" and "NameError" in texts(result)[0]["text"]
        finally:
            await reg.stop_all()

    run(go())


def test_second_run_waits_for_first(root):
    # Demonstrates: one run at a time per project
    svc, reg, pid, ids, pushes = service_with_cells(root, ["import time; time.sleep(2); a = 1", "b = a + 1"])

    async def go():
        try:
            await reg.start(pid, files(root, pid))
            first = asyncio.create_task(svc.run_cell(pid, 0, ids[0], "import time; time.sleep(2); a = 1"))
            await asyncio.sleep(0.5)
            v = (await svc.props(pid))["version"]
            props = await svc.run_cell(pid, v, ids[1], "b = a + 1")
            await first
            assert any(p["cells"][1]["status"] == "queued" for p in pushes)
            assert [c["status"] for c in props["cells"]] == ["done", "done"]
        finally:
            await reg.stop_all()

    run(go())


def test_idle_kernel_is_stopped(root):
    # Demonstrates: no forgotten processes
    @kernel_test
    async def go(reg, root, pid):
        await exec_(reg, root, pid, "x = 1")
        reg._kernels[pid].last_used = time.monotonic() - reg.idle_minutes * 60 - 1
        await reg.stop_idle()
        assert reg.status(pid) == "off"
        result = await exec_(reg, root, pid, "1")
        assert result.status == "done" and result.execution_count == 1  # fresh kernel

    go(root)


# ---- One workspace per project · integration (kernel)
# Baseline: Given projects P and Q · When code runs in P


def test_projects_have_separate_variables(root):
    # Demonstrates: no mixing between projects
    @kernel_test
    async def go(reg, root, pid):
        qid = store.create_project("Q", root).id
        await exec_(reg, root, pid, "x = 1")
        result = await exec_(reg, root, qid, "x")
        assert result.status == "error" and "NameError" in texts(result)[0]["text"]

    go(root)


def test_two_sessions_share_one_project_workspace(root):
    # Demonstrates: one workspace per project
    svc, reg, pid, ids, pushes = service_with_cells(root, ["x = 41"])

    async def go():
        try:
            await svc.run_all(pid, 0)  # chat 1
            v = (await svc.props(pid))["version"]
            props = await svc.add_cell(pid, v, None, "code")  # chat 2, same project
            cell = props["cells"][-1]["id"]
            props = await svc.run_cell(pid, props["version"], cell, "x + 1")
            assert props["cells"][-1]["outputs"][0]["text"] == "42"
            assert list(reg._kernels) == [pid]  # one kernel
            assert pushes  # every change was pushed to the project's panels
        finally:
            await reg.stop_all()

    run(go())


def test_projects_have_separate_files_dirs(root):
    @kernel_test
    async def go(reg, root, pid):
        qid = store.create_project("Q", root).id
        await exec_(reg, root, pid, 'open("only-p.txt", "w").write("p")')
        result = await exec_(reg, root, qid, 'import os; os.path.exists("only-p.txt")')
        assert texts(result)[0]["text"] == "False"
        assert not (files(root, qid) / "only-p.txt").exists()

    go(root)


# ---- Docker sandbox · integration (`@pytest.mark.docker`)
# Baseline: Given project P's kernel container is running · When a cell runs


def test_code_runs_in_container_in_work_dir(root):
    # Demonstrates: code never runs on the host
    @kernel_test
    async def go(reg, root, pid):
        result = await exec_(reg, root, pid, 'import os; (os.getcwd(), os.path.exists("/.dockerenv"))')
        assert texts(result)[0]["text"] == "('/work', True)"

    go(root)


def test_file_written_in_cell_appears_in_project_files(root):
    @kernel_test
    async def go(reg, root, pid):
        await exec_(reg, root, pid, 'import pandas as pd; pd.DataFrame({"a": [1]}).to_csv("t.csv", index=False)')
        assert (files(root, pid) / "t.csv").read_text().splitlines() == ["a", "1"]

    go(root)


def _sleeper(reg, project_id):
    """A stand-in kernel container labelled like the registry's own."""
    name = reg.container_name(project_id)
    _docker("run", "-d", "--rm", "--name", name, "--label", f"{SCOPE_LABEL}={reg.scope}", DockerSettings().image, "sleep", "300")
    return name


def _exists(name):
    return name in _docker("ps", "-a", "--filter", f"name={name}", "--format", "{{.Names}}").stdout.split()


def test_leftover_containers_removed_on_startup(root):
    reg = make_registry(root)
    name = _sleeper(reg, "leftover")
    try:
        run(reg.cleanup_leftovers())
        assert not _exists(name)
    finally:
        _docker("rm", "-f", name)


def test_cleanup_leaves_other_apps_kernels_alone(tmp_path):
    # Demonstrates: cleanup only touches its own workspaces folder
    # (found in testing: the cleanup test removed the running app's kernel)
    mine = make_registry(tmp_path / "mine")
    other = make_registry(tmp_path / "other")
    assert mine.scope != other.scope
    assert mine.container_name("p") != other.container_name("p")
    theirs = _sleeper(other, "p")
    try:
        run(mine.cleanup_leftovers())
        assert _exists(theirs)
    finally:
        _docker("rm", "-f", theirs)


def test_host_files_are_not_visible(root):
    @kernel_test
    async def go(reg, root, pid):
        code = (
            "import os\n"
            "(sorted(os.listdir('/work')), os.path.exists('/mnt/c'), os.path.exists('/conn/kernel.json') and os.access('/conn', os.W_OK))"
        )
        result = await exec_(reg, root, pid, code)
        assert texts(result)[0]["text"] == "([], False, False)"

    go(root)


def test_container_has_no_host_env(root, monkeypatch):
    # Demonstrates: key can't leak
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-secret")
    monkeypatch.setenv("MY_TOKEN", "tok")

    @kernel_test
    async def go(reg, root, pid):
        result = await exec_(reg, root, pid, "import os, json; json.dumps(sorted(os.environ))")
        names = json.loads(texts(result)[0]["text"].strip("'"))
        assert "OPENROUTER_API_KEY" not in names and "MY_TOKEN" not in names
        assert "sk-or-test-secret" not in texts(result)[0]["text"]

    go(root)


def test_write_outside_work_fails(root):
    # read-only root
    @kernel_test
    async def go(reg, root, pid):
        result = await exec_(reg, root, pid, 'open("/etc/evil", "w")')
        assert result.status == "error"
        assert "Read-only file system" in texts(result)[0]["text"] or "Permission denied" in texts(result)[0]["text"]

    go(root)


def test_memory_hog_kills_kernel_not_app(root):
    pid = store.create_project("P", root).id
    reg = KernelRegistry(root=root, timeout_seconds=30, docker=DockerSettings(memory="256m"))

    async def go():
        try:
            with pytest.raises(WorkspaceError) as err:
                await exec_(reg, root, pid, "x = bytearray(1024 * 1024 * 1024)")
            assert err.value.code == ErrorCode.KERNEL_DEAD
            await reg.restart(pid, files(root, pid))
            assert texts(await exec_(reg, root, pid, "1+1"))[0]["text"] == "2"
        finally:
            await reg.stop_all()

    run(go())


def test_docker_down_reports_unavailable(root, monkeypatch):
    # Demonstrates: no host fallback
    from sillytherin.workspace import kernels

    async def no_docker(*args, **kwargs):
        raise OSError("docker: not reachable")

    monkeypatch.setattr(kernels, "docker", no_docker)
    pid = store.create_project("P", root).id
    reg = make_registry(root)
    with pytest.raises(WorkspaceError) as err:
        run(exec_(reg, root, pid, "open('ran-on-host.txt', 'w')"))
    assert err.value.code == ErrorCode.KERNEL_UNAVAILABLE
    assert reg.status(pid) == "unavailable"
    assert not (files(root, pid) / "ran-on-host.txt").exists() and not os.path.exists("ran-on-host.txt")


def test_kernel_ports_bound_to_localhost(root):
    @kernel_test
    async def go(reg, root, pid):
        await exec_(reg, root, pid, "1")
        info = _docker("inspect", "-f", "{{json .HostConfig.PortBindings}}", reg.container_name(pid)).stdout
        bindings = [b for spec in json.loads(info).values() for b in spec]
        assert len(bindings) == 5 and all(b["HostIp"] == "127.0.0.1" for b in bindings)

    go(root)


# ---- Shared pool · kernel arguments


def mount_specs(arguments):
    return [arguments[i + 1] for i, a in enumerate(arguments) if a == "--mount"]


class RecordingDocker:
    """Stands in for the docker CLI: records each call and refuses `run`, so no container starts."""

    def __init__(self):
        self.calls: list[tuple[str, ...]] = []

    async def __call__(self, *args, timeout=60):
        self.calls.append(args)
        failed = args[0] == "run"
        return subprocess.CompletedProcess(args, 1 if failed else 0, stdout="", stderr="refused in test")


def test_kernel_mounts_project_view_read_only_at_pool_root(root):
    # Changed: build the docker run arguments with the project's view folder
    # Then: the view is mounted read-only at /.dataset-pool, where the relative links land; still only files/ at /work
    # Demonstrates: links land on the project's own files
    reg = make_registry(root)
    view = root / VIEWS_DIR / "p"
    mounts = ContainerMounts(root / "p" / "files", root / ".kernels" / "p", view)
    specs = mount_specs(reg.run_arguments("rc-kernel-x", "p", mounts, (1, 2, 3, 4, 5)))
    assert f"type=bind,source={view},target=/.dataset-pool,readonly" in specs
    assert [m for m in specs if "target=/work" in m] == [f"type=bind,source={root / 'p' / 'files'},target=/work"]
    assert all(m.endswith(",readonly") for m in specs if "target=/work" not in m)


def test_kernel_start_syncs_the_view_first(root, monkeypatch):
    # Changed: a project created before views existed has no view folder
    # Then: before_start runs and the view is built before docker run
    # Demonstrates: old projects work without any action
    recorder = RecordingDocker()
    monkeypatch.setattr(kernels, "docker", recorder)
    reg = make_registry(root)
    pid = store.create_project("Old", root).id
    view = root / VIEWS_DIR / pid
    order = []

    async def build_view(project_id):
        order.append(("view", project_id, len(recorder.calls)))
        view.mkdir(parents=True)
        return view

    reg.before_start = build_view
    with pytest.raises(WorkspaceError):
        run(reg._start_container(pid, files(root, pid)))
    run_calls = [i for i, call in enumerate(recorder.calls) if call[0] == "run"]
    assert order and order[0][1] == pid and order[0][2] <= run_calls[0]
    assert f"type=bind,source={view.resolve()},target=/.dataset-pool,readonly" in mount_specs(recorder.calls[run_calls[0]])


def test_kernel_never_mounts_the_whole_pool(root, monkeypatch):
    # Then: no mount source is the pool folder
    # Demonstrates: the whole pool is never exposed to a kernel
    recorder = RecordingDocker()
    monkeypatch.setattr(kernels, "docker", recorder)
    reg = make_registry(root)
    pid = store.create_project("P", root).id
    with pytest.raises(WorkspaceError):
        run(reg._start_container(pid, files(root, pid)))
    [run_call] = [call for call in recorder.calls if call[0] == "run"]
    sources = [spec.split("source=")[1].split(",")[0] for spec in mount_specs(run_call)]
    pool = (root / POOL_DIR).resolve()
    assert not any(Path(source) == pool or pool.is_relative_to(source) for source in sources)


# ---- Isolation inside a real kernel · integration
# Baseline: project A lists iris and B lists zenodo-123, both kernels running; code runs in A.

IRIS, ZENODO = "hf-iris@abc1234", "zenodo-123"


def put_in_pool(root, entry_id, name, data):
    path = DatasetPool(root).pool_file_path(entry_id, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def link_into_project(root, pid, dataset_id, entry_id, name):
    link = ds.link_path(pid, dataset_id, name, root)
    link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(DatasetPool.link_target(entry_id, name), link)


class TwoProjects:
    """A lists iris, B lists zenodo-123; each kernel's view shows only its own project's files."""

    def __init__(self, root):
        self.root = root
        self.views = ProjectViews(DatasetPool(root), root)
        self.a = store.create_project("A", root).id
        self.b = store.create_project("B", root).id
        put_in_pool(root, IRIS, "a.csv", b"iris bytes")
        put_in_pool(root, ZENODO, "x", b"zenodo bytes")
        link_into_project(root, self.a, "iris", IRIS, "a.csv")
        link_into_project(root, self.b, "zenodo-123", ZENODO, "x")
        self.visible = {self.a: {ViewFile(IRIS, "a.csv")}, self.b: {ViewFile(ZENODO, "x")}}
        self.reg = make_registry(root)
        self.reg.before_start = self.sync

    async def sync(self, pid):
        return self.views.sync(pid, self.visible[pid])

    async def run_in_a(self, code):
        result = await exec_(self.reg, self.root, self.a, code)
        return texts(result)


def isolation_test(fn):
    def wrapper(root):
        async def scenario():
            projects = TwoProjects(root)
            try:
                await exec_(projects.reg, root, projects.b, "1")
                await fn(projects)
            finally:
                await projects.reg.stop_all()

        run(scenario())

    wrapper.__name__ = fn.__name__
    return wrapper


def test_own_dataset_reads_through_its_link(root):
    # Changed: read /work/datasets/iris/a.csv
    # Then: the bytes match the pool file
    # Demonstrates: a project's own dataset loads as before
    @isolation_test
    async def go(projects):
        out = await projects.run_in_a("open('/work/datasets/iris/a.csv','rb').read()")
        assert out[0]["text"] == "b'iris bytes'"

    go(root)


def test_pool_root_lists_only_own_entries(root):
    # Changed: list /.dataset-pool
    # Then: only iris's entry is there
    # Demonstrates: another project's entry is invisible
    @isolation_test
    async def go(projects):
        out = await projects.run_in_a("sorted(__import__('os').listdir('/.dataset-pool'))")
        assert out[0]["text"] == f"['{IRIS}']"

    go(root)


def test_relative_path_to_other_entry_is_not_found(root):
    # Changed: open ../../.dataset-pool/zenodo-123/x
    # Then: FileNotFoundError
    # Demonstrates: a relative path can't widen access
    @isolation_test
    async def go(projects):
        out = await projects.run_in_a(f"open('../../.dataset-pool/{ZENODO}/x','rb')")
        assert out[0]["kind"] == "error" and "FileNotFoundError" in out[0]["text"]

    go(root)


def test_symlink_created_in_work_to_other_entry_is_dangling(root):
    # Changed: make /work/l point at /.dataset-pool/zenodo-123/x and open it
    # Then: FileNotFoundError
    # Demonstrates: a link made by notebook code can't widen access
    @isolation_test
    async def go(projects):
        out = await projects.run_in_a(f"import os; os.symlink('/.dataset-pool/{ZENODO}/x', '/work/l'); open('/work/l','rb')")
        assert out[0]["kind"] == "error" and "FileNotFoundError" in out[0]["text"]

    go(root)


def test_dataset_added_while_kernel_runs_is_readable(root):
    # Changed: A's view gains a new entry after the kernel started
    # Then: the running kernel reads it without a restart
    # Demonstrates: a finished download is usable at once
    @isolation_test
    async def go(projects):
        await projects.run_in_a("1")
        link_into_project(projects.root, projects.a, "zenodo-123", ZENODO, "x")
        projects.visible[projects.a].add(ViewFile(ZENODO, "x"))
        await projects.sync(projects.a)
        out = await projects.run_in_a("open('/work/datasets/zenodo-123/x','rb').read()")
        assert out[0]["text"] == "b'zenodo bytes'"

    go(root)


# ---- Shared bytes stay read-only · integration


def test_kernel_cannot_write_a_view_file(root):
    # Changed: open a file under /.dataset-pool for writing
    # Then: OSError (read-only); the pool bytes are unchanged
    # Demonstrates: one project can't change data another project reads
    @isolation_test
    async def go(projects):
        out = await projects.run_in_a(f"open('/.dataset-pool/{IRIS}/a.csv','wb').write(b'x')")
        assert out[0]["kind"] == "error" and "Read-only file system" in out[0]["text"]
        assert DatasetPool(projects.root).pool_file_path(IRIS, "a.csv").read_bytes() == b"iris bytes"

    go(root)


def test_kernel_cannot_chmod_a_view_file(root):
    # Changed: chmod a file under /.dataset-pool
    # Then: OSError; the mode on the host is unchanged
    # Demonstrates: the shared file's permissions can't be changed from a kernel
    @isolation_test
    async def go(projects):
        pool_file = DatasetPool(projects.root).pool_file_path(IRIS, "a.csv")
        mode = pool_file.stat().st_mode
        out = await projects.run_in_a(f"import os; os.chmod('/.dataset-pool/{IRIS}/a.csv', 0o777)")
        assert out[0]["kind"] == "error"
        assert pool_file.stat().st_mode == mode

    go(root)