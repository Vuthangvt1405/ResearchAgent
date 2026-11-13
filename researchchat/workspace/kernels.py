"""One Jupyter kernel per project, each in its own Docker container.

Container: rc-kernel-<project_id>, image from [notebook.docker], non-root,
read-only root, no capabilities, only the project's files/ mounted at /work,
no host environment variables, ports bound to 127.0.0.1. The app talks to it
with jupyter_client.AsyncKernelClient and a random signing key.

Docker is called through `subprocess` in a thread, so it works with any
asyncio event loop (uvicorn on Windows may not use the Proactor loop).
"""

import ast
import asyncio
import hashlib
import json
import secrets
import shutil
import socket
import subprocess
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import nbformat
from jupyter_client.asynchronous import AsyncKernelClient
from nbformat import NotebookNode

from researchchat.config import (
    CELL_TIMEOUT_SECONDS,
    DOCKER_CPUS,
    DOCKER_IMAGE,
    DOCKER_MEMORY,
    DOCKER_PIDS_LIMIT,
    KERNEL_IDLE_MINUTES,
    MAX_IMAGE_KB,
    MAX_OUTPUT_CHARS,
    WORKSPACES_DIR,
)
from researchchat.workspace import ErrorCode, WorkspaceError
from researchchat.workspace.dataset_pool import KERNEL_POOL_ROOT, POOL_DIR

CONTAINER_PREFIX = "rc-kernel-"
SCOPE_LABEL = "researchchat.scope"  # which workspaces folder a container belongs to
PROJECT_LABEL = "researchchat.project"
WORK_DIR = "/work"
CONN_DIR = ".kernels"  # under workspaces_dir; not a valid project id, so never listed
START_TIMEOUT = 60  # seconds for the container + kernel to be ready
INTERRUPT_GRACE = 10  # seconds to wait for a cell to stop after SIGINT
TRUNCATED = "\n[output truncated]\n"

# Names of user variables, without modules, IPython helpers or _private names.
VARIABLES_EXPR = (
    "__import__('json').dumps(sorted(k for k, v in globals().items() "
    "if not k.startswith('_') and k not in ('In', 'Out', 'exit', 'quit', 'get_ipython') "
    "and type(v).__name__ != 'module'))"
)

KernelStatus = Literal["off", "starting", "idle", "busy", "dead", "unavailable"]
RunStatus = Literal["done", "error", "interrupted", "timeout"]
OnOutput = Callable[[NotebookNode], Awaitable[None]]


@dataclass
class RunResult:
    status: RunStatus
    execution_count: int | None
    outputs: list[NotebookNode] = field(default_factory=list)  # nbformat outputs, ready to save


@dataclass
class DockerSettings:
    image: str = DOCKER_IMAGE
    memory: str = DOCKER_MEMORY
    cpus: float = DOCKER_CPUS
    pids_limit: int = DOCKER_PIDS_LIMIT


@dataclass
class ContainerMounts:
    """Host folders bound into a kernel container."""

    files_dir: Path  # → /work, read-write
    conn_dir: Path  # → /conn, read-only
    pool_dir: Path  # → /.dataset-pool, read-only (NB-4)


@dataclass
class _Kernel:
    container: str
    client: AsyncKernelClient
    conn_dir: Path
    state: KernelStatus = "starting"
    last_used: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)  # one request at a time
    interrupted: bool = False


def _docker(*args: str, timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


async def docker(*args: str, timeout: float = 60) -> subprocess.CompletedProcess:
    return await asyncio.to_thread(_docker, *args, timeout=timeout)


def _free_ports(n: int) -> list[int]:
    socks = []
    try:
        for _ in range(n):
            s = socket.socket()
            s.bind(("127.0.0.1", 0))
            socks.append(s)
        return [s.getsockname()[1] for s in socks]
    finally:
        for s in socks:
            s.close()


class _Capper:
    """Keeps a run's outputs inside the size limits (AC12)."""

    def __init__(self, max_chars: int, max_image_kb: int):
        self.left = max_chars
        self.max_image_bytes = max_image_kb * 1024
        self.cut = False

    def fit(self, out: NotebookNode) -> NotebookNode | None:
        if self.cut:
            return None
        kind = out.output_type
        if kind in ("display_data", "execute_result"):
            png = out.data.get("image/png")
            if png is not None and len(png) * 3 // 4 > self.max_image_bytes:
                return nbformat.v4.new_output("stream", name="stderr", text="[image too large to show]\n")
            if png is not None:
                return out
            text = "".join(str(v) for v in out.data.values() if isinstance(v, str))
        elif kind == "stream":
            text = out.text
        else:  # error
            text = "\n".join(out.get("traceback", []))
        if len(text) <= self.left:
            self.left -= len(text)
            return out
        # Too big: keep what fits as plain text, then stop collecting
        self.cut = True
        keep = text[: max(self.left, 0)]
        self.left = 0
        return nbformat.v4.new_output("stream", name="stdout" if kind != "error" else "stderr", text=keep + TRUNCATED)


class KernelRegistry:
    """Starts, runs, interrupts and stops the per-project kernel containers."""

    def __init__(
        self,
        docker: DockerSettings | None = None,
        timeout_seconds: int = CELL_TIMEOUT_SECONDS,
        idle_minutes: int = KERNEL_IDLE_MINUTES,
        max_output_chars: int = MAX_OUTPUT_CHARS,
        max_image_kb: int = MAX_IMAGE_KB,
        root: Path = WORKSPACES_DIR,
    ):
        self.docker = docker or DockerSettings()
        self.timeout_seconds = timeout_seconds
        self.idle_minutes = idle_minutes
        self.max_output_chars = max_output_chars
        self.max_image_kb = max_image_kb
        self.root = Path(root)
        # Containers belong to one workspaces folder. Cleanup only touches this
        # scope, so tests or a second app never remove each other's kernels.
        self.scope = hashlib.sha1(str(self.root.resolve()).lower().encode()).hexdigest()[:8]
        self._kernels: dict[str, _Kernel] = {}
        self._starting: dict[str, asyncio.Lock] = {}
        self._unavailable = False
        self._reaper: asyncio.Task | None = None

    # ---- status ----

    async def docker_available(self) -> bool:
        """True when the Docker engine answers. Never falls back to the host."""
        try:
            ok = (await docker("info", "--format", "{{.ServerVersion}}", timeout=15)).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            ok = False
        self._unavailable = not ok
        return ok

    def status(self, project_id: str) -> KernelStatus:
        kernel = self._kernels.get(project_id)
        if kernel:
            return kernel.state
        return "unavailable" if self._unavailable else "off"

    def container_name(self, project_id: str) -> str:
        return f"{CONTAINER_PREFIX}{self.scope}-{project_id}"

    # ---- lifecycle ----

    async def start(self, project_id: str, files_dir: Path) -> None:
        """Write a connection file and `docker run` the kernel container."""
        async with self._starting.setdefault(project_id, asyncio.Lock()):
            kernel = self._kernels.get(project_id)
            if kernel and kernel.state in ("idle", "busy"):
                return
            if kernel:
                await self.stop(project_id)
            if not await self.docker_available():
                raise WorkspaceError(
                    ErrorCode.KERNEL_UNAVAILABLE, "Docker isn't running: start Docker Desktop, then press Restart."
                )
            await self._start_container(project_id, Path(files_dir))
        self._ensure_reaper()

    async def _start_container(self, project_id: str, files_dir: Path) -> None:
        name = self.container_name(project_id)
        await docker("rm", "-f", name)

        conn_dir = self.root / CONN_DIR / project_id
        conn_dir.mkdir(parents=True, exist_ok=True)
        shell, iopub, stdin, control, hb = _free_ports(5)
        info = {
            "shell_port": shell, "iopub_port": iopub, "stdin_port": stdin,
            "control_port": control, "hb_port": hb,
            "key": secrets.token_hex(32), "signature_scheme": "hmac-sha256",
            "transport": "tcp", "kernel_name": "python3",
        }
        # Inside the container the kernel listens on all its interfaces;
        # Docker only publishes those ports on the host's 127.0.0.1.
        (conn_dir / "kernel.json").write_text(json.dumps({**info, "ip": "0.0.0.0"}), encoding="utf-8")

        files_dir.mkdir(parents=True, exist_ok=True)
        pool_dir = self.root / POOL_DIR
        pool_dir.mkdir(parents=True, exist_ok=True)  # docker refuses to bind a missing folder
        mounts = ContainerMounts(files_dir.resolve(), conn_dir.resolve(), pool_dir.resolve())
        result = await docker(*self.run_arguments(name, project_id, mounts, (shell, iopub, stdin, control, hb)), timeout=120)
        if result.returncode != 0:
            shutil.rmtree(conn_dir, ignore_errors=True)
            detail = (result.stderr or result.stdout).strip().splitlines()[-1:] or ["unknown error"]
            raise WorkspaceError(ErrorCode.KERNEL_DEAD, f"Couldn't start the kernel: {detail[0]}")

        client = AsyncKernelClient()
        client.load_connection_info({**info, "ip": "127.0.0.1"})
        client.start_channels()
        kernel = _Kernel(name, client, conn_dir)
        self._kernels[project_id] = kernel
        try:
            await client.wait_for_ready(timeout=START_TIMEOUT)
        except Exception as e:
            await self.stop(project_id)
            raise WorkspaceError(ErrorCode.KERNEL_DEAD, "The kernel didn't start in time.") from e
        kernel.state = "idle"

    def run_arguments(self, name: str, project_id: str, mounts: ContainerMounts, ports: tuple[int, ...]) -> list[str]:
        """The `docker run` arguments for one kernel: /work read-write, /conn and the dataset pool read-only (AC18)."""
        published = [arg for p in ports for arg in ("-p", f"127.0.0.1:{p}:{p}")]
        return [
            "run", "-d", "--rm", "--init", "--name", name,
            "--label", f"{SCOPE_LABEL}={self.scope}", "--label", f"{PROJECT_LABEL}={project_id}",
            "--user", "1000",
            "--read-only", "--tmpfs", "/tmp",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--memory", str(self.docker.memory), "--memory-swap", str(self.docker.memory),
            "--cpus", str(self.docker.cpus), "--pids-limit", str(self.docker.pids_limit),
            "--mount", f"type=bind,source={mounts.files_dir},target={WORK_DIR}",
            "--mount", f"type=bind,source={mounts.conn_dir},target=/conn,readonly",
            # Project links into the pool are relative and land here (dataset_pool.py)
            "--mount", f"type=bind,source={mounts.pool_dir},target={KERNEL_POOL_ROOT},readonly",
            "-w", WORK_DIR,
            *published,
            self.docker.image,
            "python", "-m", "ipykernel_launcher", "-f", "/conn/kernel.json",
        ]

    async def _running(self, kernel: _Kernel) -> bool:
        result = await docker("inspect", "-f", "{{.State.Running}}", kernel.container, timeout=15)
        return result.returncode == 0 and result.stdout.strip() == "true"

    async def _kernel(self, project_id: str, files_dir: Path | None) -> _Kernel:
        kernel = self._kernels.get(project_id)
        if kernel and kernel.state == "dead":
            raise WorkspaceError(ErrorCode.KERNEL_DEAD, "The kernel died (maybe out of memory): press Restart.")
        if not kernel or kernel.state in ("off", "starting"):
            await self.start(project_id, files_dir or self.root / project_id / "files")
            kernel = self._kernels[project_id]
        return kernel

    # ---- running code ----

    async def execute(self, project_id: str, code: str, on_output: OnOutput, files_dir: Path | None = None) -> RunResult:
        """Run code, stream each output to on_output, interrupt at the time limit."""
        kernel = await self._kernel(project_id, files_dir)
        async with kernel.lock:
            kernel.state = "busy"
            kernel.interrupted = False
            kernel.last_used = time.monotonic()
            capper = _Capper(self.max_output_chars, self.max_image_kb)
            outputs: list[NotebookNode] = []
            timed_out = False
            try:
                msg_id = kernel.client.execute(code, store_history=True, allow_stdin=False)
                deadline = time.monotonic() + self.timeout_seconds
                while True:
                    now = time.monotonic()
                    if not timed_out and now > deadline:
                        timed_out = True
                        await self.interrupt(project_id)
                        deadline = now + INTERRUPT_GRACE
                    elif timed_out and now > deadline:
                        raise WorkspaceError(ErrorCode.KERNEL_DEAD, "The kernel stopped responding: press Restart.")
                    try:
                        msg = await kernel.client.get_iopub_msg(timeout=1)
                    except Exception:  # queue.Empty: nothing yet
                        if not await self._running(kernel):
                            kernel.state = "dead"
                            raise WorkspaceError(ErrorCode.KERNEL_DEAD, "The kernel died (maybe out of memory): press Restart.")
                        continue
                    if msg.get("parent_header", {}).get("msg_id") != msg_id:
                        continue
                    kind = msg["msg_type"]
                    if kind == "status" and msg["content"]["execution_state"] == "idle":
                        break
                    if kind in ("stream", "execute_result", "display_data", "error"):
                        out = capper.fit(nbformat.v4.output_from_msg(msg))
                        if out is None:
                            continue
                        if out.output_type == "stream" and outputs and outputs[-1].output_type == "stream" and outputs[-1].name == out.name:
                            outputs[-1].text += out.text  # join printed lines into one output
                        else:
                            outputs.append(out)
                        await on_output(out)
                    if kind == "clear_output":
                        outputs.clear()
                while True:  # skip any stray reply that isn't for this request
                    reply = await kernel.client.get_shell_msg(timeout=10)
                    if reply.get("parent_header", {}).get("msg_id") == msg_id:
                        break
                content = reply["content"]
                count = content.get("execution_count")
                if timed_out:
                    status: RunStatus = "timeout"
                    outputs.append(nbformat.v4.new_output("stream", name="stderr", text=f"[Timed out after {self.timeout_seconds} s]\n"))
                elif kernel.interrupted:
                    status = "interrupted"
                else:
                    status = "done" if content.get("status") == "ok" else "error"
                return RunResult(status, count, outputs)
            finally:
                if kernel.state == "busy":
                    kernel.state = "idle"
                kernel.last_used = time.monotonic()

    async def variables(self, project_id: str) -> list[str] | None:
        """Names of user variables, via a silent user_expressions request.

        Doesn't change execution_count. None when the kernel is busy or off.
        """
        kernel = self._kernels.get(project_id)
        if not kernel or kernel.state != "idle" or kernel.lock.locked():
            return None
        async with kernel.lock:
            msg_id = kernel.client.execute("", silent=True, store_history=False, user_expressions={"v": VARIABLES_EXPR})
            for _ in range(20):
                reply = await kernel.client.get_shell_msg(timeout=10)
                if reply.get("parent_header", {}).get("msg_id") == msg_id:
                    break
            value = reply["content"].get("user_expressions", {}).get("v", {})
            if value.get("status") != "ok":
                return None
            return json.loads(ast.literal_eval(value["data"]["text/plain"]))

    async def interrupt(self, project_id: str) -> None:
        """Stop the running cell; variables are kept."""
        kernel = self._kernels.get(project_id)
        if kernel and kernel.state == "busy":
            kernel.interrupted = True
            await docker("kill", "--signal", "SIGINT", kernel.container, timeout=15)

    async def restart(self, project_id: str, files_dir: Path) -> None:
        """Remove the container and start a fresh one (variables cleared)."""
        await self.stop(project_id)
        await self.start(project_id, files_dir)

    async def stop(self, project_id: str) -> None:
        kernel = self._kernels.pop(project_id, None)
        if kernel:
            kernel.client.stop_channels()
            shutil.rmtree(kernel.conn_dir, ignore_errors=True)
        await docker("rm", "-f", self.container_name(project_id), timeout=30)

    async def stop_all(self) -> None:
        for project_id in list(self._kernels):
            await self.stop(project_id)

    async def stop_idle(self) -> None:
        """Stop kernels idle longer than idle_minutes."""
        limit = self.idle_minutes * 60
        for project_id, kernel in list(self._kernels.items()):
            if kernel.state == "idle" and not kernel.lock.locked() and time.monotonic() - kernel.last_used > limit:
                await self.stop(project_id)

    def _ensure_reaper(self) -> None:
        if self.idle_minutes > 0 and (self._reaper is None or self._reaper.done()):
            self._reaper = asyncio.create_task(self._reap())

    async def _reap(self) -> None:
        while self._kernels:
            await asyncio.sleep(60)
            await self.stop_idle()

    async def cleanup_leftovers(self) -> None:
        """Remove this workspaces folder's kernel containers left from a previous app run."""
        try:
            listed = await docker(
                "ps", "-a", "--filter", f"label={SCOPE_LABEL}={self.scope}", "--format", "{{.Names}}", timeout=15
            )
        except (OSError, subprocess.TimeoutExpired):
            return
        live = {self.container_name(pid) for pid in self._kernels}
        for name in listed.stdout.split():
            if name not in live:
                await docker("rm", "-f", name, timeout=30)
        conn_root = self.root / CONN_DIR
        if conn_root.is_dir():
            for folder in conn_root.iterdir():
                if folder.name not in self._kernels:
                    shutil.rmtree(folder, ignore_errors=True)
