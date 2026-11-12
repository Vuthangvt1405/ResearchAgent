"""Shared test helpers for the notebook workspace."""

import nbformat
import pytest

from researchchat.workspace.kernels import RunResult
from researchchat.workspace.service import NotebookService


class FakeKernels:
    """Stands in for KernelRegistry: no Docker, records what would run."""

    def __init__(self):
        self.executed: list[str] = []
        self.count = 0
        self.results: dict[str, tuple[str, list]] = {}  # code -> (status, outputs)
        self.vars: list[str] | None = []
        self.state = "idle"

    def status(self, project_id):
        return self.state

    async def execute(self, project_id, code, on_output, files_dir=None):
        self.executed.append(code)
        self.count += 1
        status, outputs = self.results.get(
            code, ("done", [nbformat.v4.new_output("execute_result", {"text/plain": f"ran {code}"}, execution_count=self.count)])
        )
        for out in outputs:
            await on_output(out)
        return RunResult(status, self.count, list(outputs))

    async def variables(self, project_id):
        return self.vars

    async def interrupt(self, project_id):
        pass

    async def restart(self, project_id, files_dir):
        self.count = 0


def _docker_ready() -> str | None:
    """None when Docker and the kernel image are ready, else why not."""
    import subprocess

    from researchchat.config import DOCKER_IMAGE

    try:
        if subprocess.run(["docker", "info"], capture_output=True, timeout=15).returncode != 0:
            return "Docker isn't running (start Docker Desktop)"
        if subprocess.run(["docker", "image", "inspect", DOCKER_IMAGE], capture_output=True, timeout=15).returncode != 0:
            return f"kernel image {DOCKER_IMAGE} not built (see README)"
    except (OSError, subprocess.TimeoutExpired):
        return "Docker isn't installed"
    return None


def pytest_collection_modifyitems(config, items):
    docker_items = [i for i in items if i.get_closest_marker("docker")]
    if not docker_items:
        return
    reason = _docker_ready()
    if reason:
        for item in docker_items:
            item.add_marker(pytest.mark.skip(reason=reason))


@pytest.fixture
def fake_kernels():
    return FakeKernels()


@pytest.fixture
def service_factory(fake_kernels):
    def make(root):
        return NotebookService(fake_kernels, root=root)

    return make


# ---- NB-3 dataset download helpers (plan §7 test infrastructure) -----------------


async def fake_lookup(host: str) -> list[str]:
    """Stands in for dataset_sources.lookup_host: IP literals as is, names -> a public address."""
    import ipaddress

    try:
        return [str(ipaddress.ip_address(host))]
    except ValueError:
        return ["93.184.216.34"]


def catalog_client(handler):
    """An httpx client whose requests go to `handler` (no network)."""
    import httpx

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class FakeFreeDisk:
    """Free disk as a mutable callable; tests lower `free` between chunks."""

    def __init__(self, free: int):
        self.free = free

    def __call__(self, path) -> int:
        return self.free


class FakeChats:
    """Captures chat messages a background job sends: (session_id, text)."""

    def __init__(self, open_sessions=("s1",)):
        self.open = set(open_sessions)
        self.sent: list[tuple[str, str]] = []

    async def send(self, session_id: str, text: str) -> bool:
        if session_id not in self.open:
            return False
        self.sent.append((session_id, text))
        return True


class FakeDatasetService:
    """Stands in for DatasetService in tool tests: records calls, returns canned DTOs."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.started = None  # DownloadStarted to return from request()
        self.records: list = []  # DatasetRecordView list for list_for_model()
        self.error = None  # WorkspaceError to raise from request()

    async def request(self, project_id, session_id, ref, files=None, update=False, *, approve):
        self.calls.append(("request", project_id, session_id, ref, files, update))
        if self.error:
            raise self.error
        return self.started

    def list_for_model(self, project_id):
        self.calls.append(("list", project_id))
        return self.records

    def describe(self, project_id, dataset_id):
        self.calls.append(("describe", project_id, dataset_id))
        return next(r for r in self.records if r["dataset_id"] == dataset_id)

    async def delete(self, project_id, dataset_id):
        self.calls.append(("delete", project_id, dataset_id))
        return {"deleted": dataset_id, "freed_bytes": 0}
