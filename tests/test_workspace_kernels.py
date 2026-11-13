"""Running code in the Docker kernel (needs Docker).

Plan: docs/plans/done/notebook-workspace-plan.md section 7.
These start real kernel containers; they skip when Docker or the image is missing.
"""

import asyncio
import json
import os
import time

import nbformat
import pytest

from researchchat.workspace import ErrorCode, WorkspaceError, store
from researchchat.workspace.kernels import SCOPE_LABEL, ContainerMounts, DockerSettings, KernelRegistry, _docker
from researchchat.workspace.service import NotebookService, output_props

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


# ---- Group 3: Running code (AC2, AC3, AC4, AC12, AC13, AC14, AC16) · integration (kernel)
# Baseline: Given project P with a running kernel · When a cell is executed


def test_run_shows_last_value_and_execution_count(root):
    # G3✅1 (baseline) · Demonstrates: basic Jupyter behaviour
    @kernel_test
    async def go(reg, root, pid):
        result = await exec_(reg, root, pid, "1+1")
        assert result.status == "done" and result.execution_count == 1
        assert texts(result) == [{"kind": "result", "text": "2", "image": ""}]

    go(root)


def test_print_goes_to_stdout_output(root):
    # G3✅2 (edge)
    @kernel_test
    async def go(reg, root, pid):
        result = await exec_(reg, root, pid, 'print("hi")')
        assert texts(result) == [{"kind": "stdout", "text": "hi\n", "image": ""}]

    go(root)


def test_variables_persist_between_cells(root):
    # G3✅3 (edge) · Demonstrates: one session per project
    @kernel_test
    async def go(reg, root, pid):
        await exec_(reg, root, pid, "x = 5")
        result = await exec_(reg, root, pid, "x * 2")
        assert texts(result)[0]["text"] == "10" and result.execution_count == 2

    go(root)


def test_matplotlib_chart_becomes_png_output(root):
    # G3✅4 (edge) · Demonstrates: charts work
    @kernel_test
    async def go(reg, root, pid):
        result = await exec_(reg, root, pid, "import matplotlib.pyplot as plt\nplt.plot([1, 3, 2])\nplt.show()")
        images = [o for o in texts(result) if o["kind"] == "image"]
        assert result.status == "done" and len(images) == 1
        assert images[0]["image"].startswith("iVBOR")  # base64 PNG

    go(root)


def test_relative_paths_use_project_files_dir(root):
    # G3✅5 (edge)
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
    # G3✅6 (edge) · Demonstrates: Jupyter's run-all behaviour
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
    # G3✅7 (edge)
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
    # G3✅8 (edge) · Demonstrates: the panel can scroll it sideways (AC14)
    @kernel_test
    async def go(reg, root, pid):
        result = await exec_(reg, root, pid, 'print("x" * 2000)')
        assert texts(result)[0]["text"] == "x" * 2000 + "\n"

    go(root)


def test_exception_shows_traceback_and_error_status(root):
    # G3❌1 (negative) · Demonstrates: errors don't kill the session
    @kernel_test
    async def go(reg, root, pid):
        result = await exec_(reg, root, pid, "1/0")
        out = texts(result)
        assert result.status == "error" and out[0]["kind"] == "error"
        assert "ZeroDivisionError" in out[0]["text"] and "\x1b[" not in out[0]["text"]
        assert texts(await exec_(reg, root, pid, "1+1"))[0]["text"] == "2"

    go(root)


def test_long_output_is_truncated(root):
    # G3❌2 (negative)
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
    # G3❌3 (negative) · (S6)
    @kernel_test
    async def go(reg, root, pid):
        result = await exec_(reg, root, pid, 'from IPython.display import HTML, display\ndisplay(HTML("<script>alert(1)</script>"))')
        out = texts(result)
        assert all(o["kind"] in ("stdout", "stderr", "result", "image", "error") for o in out)
        assert out[0]["kind"] == "result" and "<IPython.core.display.HTML object>" in out[0]["text"]

    go(root)


def test_dead_kernel_is_reported_and_restartable(root):
    # G3❌4 (negative)
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


# ---- Group 4: Interrupt, timeout, restart (AC8, AC9) · integration (kernel)
# Baseline: Given `x = 1` ran in P · When a long cell `while True: pass` runs


def test_interrupt_stops_run_and_keeps_variables(root):
    # G4✅1 (baseline) · Demonstrates: Stop doesn't lose work
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
    # G4❌1 (negative) · Demonstrates: runaway code is stopped
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
    # G4✅2 (edge)
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
    # G4✅3 (edge) · Demonstrates: one run at a time per project
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
    # G4✅4 (edge) · Demonstrates: no forgotten processes
    @kernel_test
    async def go(reg, root, pid):
        await exec_(reg, root, pid, "x = 1")
        reg._kernels[pid].last_used = time.monotonic() - reg.idle_minutes * 60 - 1
        await reg.stop_idle()
        assert reg.status(pid) == "off"
        result = await exec_(reg, root, pid, "1")
        assert result.status == "done" and result.execution_count == 1  # fresh kernel

    go(root)


# ---- Group 5: One workspace per project (AC6, AC7) · integration (kernel)
# Baseline: Given projects P and Q · When code runs in P


def test_projects_have_separate_variables(root):
    # G5✅1 (baseline) · Demonstrates: no mixing between projects
    @kernel_test
    async def go(reg, root, pid):
        qid = store.create_project("Q", root).id
        await exec_(reg, root, pid, "x = 1")
        result = await exec_(reg, root, qid, "x")
        assert result.status == "error" and "NameError" in texts(result)[0]["text"]

    go(root)


def test_two_sessions_share_one_project_workspace(root):
    # G5✅2 (edge) · Demonstrates: one workspace per project
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
    # G5✅3 (edge)
    @kernel_test
    async def go(reg, root, pid):
        qid = store.create_project("Q", root).id
        await exec_(reg, root, pid, 'open("only-p.txt", "w").write("p")')
        result = await exec_(reg, root, qid, 'import os; os.path.exists("only-p.txt")')
        assert texts(result)[0]["text"] == "False"
        assert not (files(root, qid) / "only-p.txt").exists()

    go(root)


# ---- Group 9: Docker sandbox (AC19, AC20) · integration (`@pytest.mark.docker`)
# Baseline: Given project P's kernel container is running · When a cell runs


def test_code_runs_in_container_in_work_dir(root):
    # G9✅1 (baseline) · Demonstrates: code never runs on the host
    @kernel_test
    async def go(reg, root, pid):
        result = await exec_(reg, root, pid, 'import os; (os.getcwd(), os.path.exists("/.dockerenv"))')
        assert texts(result)[0]["text"] == "('/work', True)"

    go(root)


def test_file_written_in_cell_appears_in_project_files(root):
    # G9✅2 (edge)
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
    # G9✅3 (edge)
    reg = make_registry(root)
    name = _sleeper(reg, "leftover")
    try:
        run(reg.cleanup_leftovers())
        assert not _exists(name)
    finally:
        _docker("rm", "-f", name)


def test_cleanup_leaves_other_apps_kernels_alone(tmp_path):
    # G9✅4 (edge) · Demonstrates: cleanup only touches its own workspaces folder
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
    # G9❌1 (negative) · (#10)
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
    # G9❌2 (negative) · Demonstrates: key can't leak (#4)
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
    # G9❌3 (negative) · read-only root (#10)
    @kernel_test
    async def go(reg, root, pid):
        result = await exec_(reg, root, pid, 'open("/etc/evil", "w")')
        assert result.status == "error"
        assert "Read-only file system" in texts(result)[0]["text"] or "Permission denied" in texts(result)[0]["text"]

    go(root)


def test_memory_hog_kills_kernel_not_app(root):
    # G9❌4 (negative) · (#7)
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
    # G9❌5 (negative) · Demonstrates: no host fallback (AC20)
    from researchchat.workspace import kernels

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
    # G9❌6 (negative) · (#11)
    @kernel_test
    async def go(reg, root, pid):
        await exec_(reg, root, pid, "1")
        info = _docker("inspect", "-f", "{{json .HostConfig.PortBindings}}", reg.container_name(pid)).stdout
        bindings = [b for spec in json.loads(info).values() for b in spec]
        assert len(bindings) == 5 and all(b["HostIp"] == "127.0.0.1" for b in bindings)

    go(root)


# ---- NB-4 Group 11: Shared pool · kernel arguments


def test_kernel_mounts_pool_read_only(root):
    # G11✅4 · Changed: build the docker run arguments
    # Then: the pool is mounted read-only (at /.dataset-pool, where the relative links land); still only files/ at /work
    # Demonstrates: the pool can't be changed from a kernel
    reg = make_registry(root)
    mounts = ContainerMounts(root / "p" / "files", root / ".kernels" / "p", root / ".dataset-pool")
    args = reg.run_arguments("rc-kernel-x", "p", mounts, (1, 2, 3, 4, 5))
    mount_specs = [args[i + 1] for i, a in enumerate(args) if a == "--mount"]
    assert f"type=bind,source={root / '.dataset-pool'},target=/.dataset-pool,readonly" in mount_specs
    assert [m for m in mount_specs if "target=/work" in m] == [f"type=bind,source={root / 'p' / 'files'},target=/work"]
    assert all(m.endswith(",readonly") for m in mount_specs if "target=/work" not in m)
