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
