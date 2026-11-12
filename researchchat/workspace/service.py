"""Edit and run notebooks under a per-project lock, and build panel props.

Every edit carries the version the panel last saw; a mismatch is STALE and
the latest notebook comes back instead (plan §4.2).

Two locks per project: `edit` (short, guards the .ipynb file) and `run`
(one run at a time, later runs wait in order). Typing still saves while a
cell runs, because a run only holds the edit lock at its start and end.
"""

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Literal, TypedDict

from nbformat import NotebookNode

from researchchat.config import NOTEBOOK_READ_MAX_CHARS, WORKSPACES_DIR
from researchchat.workspace import ErrorCode, WorkspaceError
from researchchat.workspace import store
from researchchat.workspace.kernels import KernelRegistry, KernelStatus, RunResult
from researchchat.workspace.store import CellType, Direction

CellStatus = Literal["idle", "queued", "running", "done", "error", "interrupted", "timeout"]
OutputKind = Literal["stdout", "stderr", "result", "image", "error"]

MODEL_OUTPUT_MAX_CHARS = 4000
PUSH_INTERVAL = 0.25  # seconds between live output pushes
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


# ---- NotebookProps (server -> panel), plan §4.3 -------------------------------


class ProjectRef(TypedDict):
    id: str  # which workspace the panel shows (folder name)
    name: str  # friendly name for the header and project bar


class OutputProps(TypedDict):
    kind: OutputKind  # how to render it
    text: str  # stdout/stderr/result text, or a traceback
    image: str  # base64 PNG for kind == "image"


class CellProps(TypedDict):
    id: str  # stable nbformat id, survives reordering
    type: CellType  # code runs in the kernel; markdown is a note, never run
    source: str  # the code, or the note's Markdown (<= 100 KB)
    execution_count: int | None  # the [n] label; always None for notes
    status: CellStatus  # the cell's badge
    outputs: list[OutputProps]  # what to show under the cell; empty for notes


class ErrorProps(TypedDict):
    code: str  # an ErrorCode value
    message: str  # one-line banner text


DatasetPanelStatus = Literal["queued", "downloading", "ready", "failed", "missing"]


class DatasetProps(TypedDict):
    """One row of the panel's Datasets section (NB-3 plan §4.3)."""

    id: str  # sent back in ds_delete / ds_cancel
    name: str  # row title
    source: str  # source badge (huggingface / zenodo)
    status: DatasetPanelStatus  # badge while not ready; a ready row has no badge (AC21)
    done_bytes: int | None  # progress bar while downloading
    position_in_queue: int | None  # "2nd in queue" while queued
    license: str | None  # chip while downloading, and in the details
    size_bytes: int  # "143.8 MB"
    file_count: int  # "· 1 file" when ready
    url: str | None  # source link in the details (only if https:)
    path: str  # copy-able /work/datasets/<id> path
    downloaded_at: str | None  # "added 2 h ago"
    error: str | None  # red line when failed


class NotebookProps(TypedDict):
    project: ProjectRef
    version: int  # sent back with edits so stale ones are rejected
    kernel: KernelStatus  # status dot; enables Stop / Restart
    running_cell_id: str | None  # which cell shows the spinner
    cells: list[CellProps]
    error: ErrorProps | None  # set when the action was rejected
    datasets: list[DatasetProps]  # NB-3: the project's datasets
    datasets_rev: int  # NB-3: bumps on every dataset change, so the panel keeps the newest list (SEC16)


Notify = Callable[[str, NotebookProps], Awaitable[None]]
DatasetState = Callable[[str], tuple[list[DatasetProps], int]]  # project_id -> (datasets, datasets_rev)


# ---- output conversion ----------------------------------------------------------


def _text(value) -> str:
    return "".join(value) if isinstance(value, list) else str(value or "")


def output_props(out: NotebookNode) -> OutputProps:
    """One nbformat output -> what the panel draws. HTML is never rendered."""
    kind = out.get("output_type")
    if kind == "stream":
        text = _text(out.get("text")).replace("\r\n", "\n")  # shell commands print CRLF
        return {"kind": "stderr" if out.get("name") == "stderr" else "stdout", "text": text, "image": ""}
    if kind == "error":
        trace = "\n".join(out.get("traceback") or []) or f"{out.get('ename')}: {out.get('evalue')}"
        return {"kind": "error", "text": ANSI_RE.sub("", trace), "image": ""}
    data = out.get("data", {})
    if "image/png" in data:
        return {"kind": "image", "text": "", "image": _text(data["image/png"]).strip()}
    for mime in ("text/plain", "text/markdown", "text/html"):
        if mime in data:
            return {"kind": "result", "text": _text(data[mime]), "image": ""}
    return {"kind": "result", "text": "[output type not shown]", "image": ""}


def _status(cell: NotebookNode) -> CellStatus:
    return cell.metadata.get("researchchat", {}).get("status", "idle")


def _set_status(cell: NotebookNode, status: CellStatus) -> None:
    cell.metadata.setdefault("researchchat", {})["status"] = status


def _image_size(b64: str) -> str:
    """'WxH' of a base64 PNG, read from its header."""
    import base64

    try:
        head = base64.b64decode(b64[:64] + "=" * (-len(b64[:64]) % 4))
        return f"{int.from_bytes(head[16:20], 'big')}x{int.from_bytes(head[20:24], 'big')}"
    except Exception:
        return "?x?"


def outputs_as_text(outputs: list[OutputProps]) -> str:
    """Outputs as plain text for the model; images are described, not sent."""
    parts = []
    for o in outputs:
        if o["kind"] == "image":
            parts.append(f"[image {_image_size(o['image'])}]")
        else:
            parts.append(o["text"].rstrip("\n"))
    return "\n".join(p for p in parts if p)


def trim(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[cut off at {limit:,} characters]"


class NotebookService:
    """The only place that changes notebooks or runs code."""

    def __init__(
        self,
        kernels: KernelRegistry,
        root: Path = WORKSPACES_DIR,
        notify: Notify | None = None,
        datasets: DatasetState | None = None,
    ):
        self.kernels = kernels
        self.root = root
        self.notify = notify
        self.datasets = datasets  # set by actions.py after DatasetService is built (plan §2.1)
        self._edit_locks: dict[str, asyncio.Lock] = {}
        self._run_locks: dict[str, asyncio.Lock] = {}
        self._running: dict[str, str] = {}  # project_id -> running cell id
        self._queued: dict[str, list[str]] = {}  # project_id -> waiting cell ids
        self._live: dict[str, list[OutputProps]] = {}  # cell id -> outputs so far

    # ---- helpers ----

    def _edit_lock(self, pid: str) -> asyncio.Lock:
        return self._edit_locks.setdefault(pid, asyncio.Lock())

    def _run_lock(self, pid: str) -> asyncio.Lock:
        return self._run_locks.setdefault(pid, asyncio.Lock())

    def _props(self, pid: str, nb: NotebookNode, error: WorkspaceError | None = None) -> NotebookProps:
        project = store.get_project(pid, self.root)
        datasets, datasets_rev = self.datasets(pid) if self.datasets else ([], 0)
        running = self._running.get(pid)
        queued = self._queued.get(pid, [])
        cells: list[CellProps] = []
        for cell in nb.cells:
            is_code = cell.cell_type == "code"
            status = "running" if cell.id == running else "queued" if cell.id in queued else _status(cell)
            outputs = self._live.get(cell.id) if cell.id == running else [output_props(o) for o in cell.get("outputs", [])]
            cells.append(
                {
                    "id": cell.id,
                    "type": "code" if is_code else "markdown",
                    "source": _text(cell.source),
                    "execution_count": cell.get("execution_count") if is_code else None,
                    "status": status if is_code else "idle",
                    "outputs": (outputs or []) if is_code else [],
                }
            )
        return {
            "project": {"id": project.id, "name": project.name},
            "version": store.get_version(nb),
            "kernel": self.kernels.status(pid),
            "running_cell_id": running,
            "cells": cells,
            "error": {"code": error.code, "message": error.message} if error else None,
            "datasets": datasets,
            "datasets_rev": datasets_rev,
        }

    async def _push(self, pid: str, props: NotebookProps) -> None:
        if self.notify:
            await self.notify(pid, props)

    async def _change(self, pid: str, version: int | None, change: Callable[[NotebookNode], None]) -> NotebookProps:
        """Load, check the version, apply `change`, bump, save, push."""
        async with self._edit_lock(pid):
            nb = store.load_notebook(pid, self.root)
            if version is not None and version != store.get_version(nb):
                raise WorkspaceError(ErrorCode.STALE, "Notebook changed, reloaded.")
            change(nb)
            store.bump_version(nb)
            store.save_notebook(pid, nb, self.root)
            props = self._props(pid, nb)
        await self._push(pid, props)
        return props

    # ---- reading ----

    async def props(self, project_id: str, error: WorkspaceError | None = None) -> NotebookProps:
        """Current state of a project's notebook for the panel."""
        nb = store.load_notebook(project_id, self.root)
        return self._props(project_id, nb, error)

    # ---- editing (all check `version`) ----

    async def add_cell(self, project_id: str, version: int, after_id: str | None, cell_type: CellType) -> NotebookProps:
        return await self._change(project_id, version, lambda nb: store.add_cell(nb, cell_type, after_id))

    async def update_cell(self, project_id: str, version: int, cell_id: str, source: str) -> NotebookProps:
        return await self._change(project_id, version, lambda nb: store.update_cell(nb, cell_id, source))

    async def delete_cell(self, project_id: str, version: int, cell_id: str) -> NotebookProps:
        return await self._change(project_id, version, lambda nb: store.delete_cell(nb, cell_id))

    async def move_cell(self, project_id: str, version: int, cell_id: str, direction: Direction) -> NotebookProps:
        return await self._change(project_id, version, lambda nb: store.move_cell(nb, cell_id, direction))

    async def clear_outputs(self, project_id: str, version: int) -> NotebookProps:
        return await self._change(project_id, version, store.clear_outputs)

    # ---- running ----

    async def run_cell(self, project_id: str, version: int, cell_id: str, source: str) -> NotebookProps:
        """Save the source, run it, push outputs to every open panel of the project."""

        def save_source(nb: NotebookNode) -> None:
            cell = store.find_cell(nb, cell_id)
            if cell.cell_type != "code":
                raise WorkspaceError(ErrorCode.NOT_CODE, "Notes don't run.")
            store.update_cell(nb, cell_id, source)

        await self._change(project_id, version, save_source)
        await self._run(project_id, cell_id)
        return await self.props(project_id)

    async def _run(self, pid: str, cell_id: str) -> RunResult | None:
        """Run one saved code cell; returns None if it vanished meanwhile."""
        self._queued.setdefault(pid, []).append(cell_id)
        await self._push(pid, await self.props(pid))
        try:
            async with self._run_lock(pid):
                self._queued[pid].remove(cell_id)
                async with self._edit_lock(pid):
                    nb = store.load_notebook(pid, self.root)
                    try:
                        code = _text(store.find_cell(nb, cell_id).source)
                    except WorkspaceError:
                        return None
                self._running[pid] = cell_id
                self._live[cell_id] = []
                await self._push(pid, await self.props(pid))

                last_push = [0.0]

                async def on_output(out: NotebookNode) -> None:
                    self._live[cell_id].append(output_props(out))
                    # At most a few pushes a second; the final state is pushed on save
                    now = time.monotonic()
                    if now - last_push[0] >= PUSH_INTERVAL:
                        last_push[0] = now
                        await self._push(pid, await self.props(pid))

                try:
                    files_dir = store.project_dir(pid, self.root) / store.FILES_DIR
                    result = await self.kernels.execute(pid, code, on_output, files_dir)
                except Exception:
                    # Tell every panel the run is over (e.g. Docker not running)
                    self._running.pop(pid, None)
                    self._live.pop(cell_id, None)
                    await self._push(pid, await self.props(pid))
                    raise
                finally:
                    self._running.pop(pid, None)
                    self._live.pop(cell_id, None)

                def save_result(nb: NotebookNode) -> None:
                    try:
                        cell = store.find_cell(nb, cell_id)
                    except WorkspaceError:
                        return  # deleted while running: drop the result
                    cell.outputs = result.outputs
                    cell.execution_count = result.execution_count
                    _set_status(cell, result.status)

                await self._change(pid, None, save_result)
                return result
        finally:
            if cell_id in self._queued.get(pid, []):
                self._queued[pid].remove(cell_id)

    async def run_all(self, project_id: str, version: int) -> NotebookProps:
        """Run code cells top to bottom, skip notes, stop at the first error."""
        nb = store.load_notebook(project_id, self.root)
        if version != store.get_version(nb):
            raise WorkspaceError(ErrorCode.STALE, "Notebook changed, reloaded.")
        for cell_id in [c.id for c in nb.cells if c.cell_type == "code"]:
            result = await self._run(project_id, cell_id)
            if result is not None and result.status != "done":
                break
        return await self.props(project_id)

    async def interrupt(self, project_id: str) -> NotebookProps:
        await self.kernels.interrupt(project_id)
        return await self.props(project_id)

    async def restart(self, project_id: str) -> NotebookProps:
        """Fresh kernel: variables cleared, cells and outputs kept."""
        await self.kernels.restart(project_id, store.project_dir(project_id, self.root) / store.FILES_DIR)
        props = await self.props(project_id)
        await self._push(project_id, props)
        return props

    # ---- projects (bar under the message box) ----

    async def list_projects(self) -> list[ProjectRef]:
        return [{"id": p.id, "name": p.name} for p in store.list_projects(self.root)]

    async def create_project(self, name: str) -> NotebookProps:
        project = store.create_project(name, self.root)
        return await self.props(project.id)

    # ---- model tools ----

    async def read_for_model(self, project_id: str, max_chars: int = NOTEBOOK_READ_MAX_CHARS) -> str:
        """Cells, trimmed outputs and variable names as text (notebook_read)."""
        props = await self.props(project_id)
        blocks = []
        for cell in props["cells"]:
            if cell["type"] == "markdown":
                blocks.append(f"[note]\n{cell['source']}")
            else:
                run = f", run {cell['execution_count']}" if cell["execution_count"] else ", not run"
                out = outputs_as_text(cell["outputs"])
                blocks.append(f"[cell{run}]\n{cell['source']}" + (f"\n--- output ---\n{trim(out, 2000)}" if out else ""))
        if props["kernel"] in ("idle", "busy"):
            names = await self.kernels.variables(project_id)
            footer = "variables: " + (", ".join(names) if names else "(none)")
        else:
            footer = "variables: kernel not running"

        # Keep the newest cells whole; drop the oldest ones first
        kept: list[str] = []
        used = len(footer)
        for block in reversed(blocks):
            if used + len(block) + 2 > max_chars:
                break
            kept.insert(0, block)
            used += len(block) + 2
        dropped = len(blocks) - len(kept)
        head = [f"[{dropped} earlier cells not shown]"] if dropped else []
        return "\n\n".join(head + kept + [footer])

    async def run_for_model(self, project_id: str, code: str) -> str:
        """Add a code cell at the end, run it, return trimmed output text (notebook_run)."""
        added: dict[str, str] = {}

        def add(nb: NotebookNode) -> None:
            cell = store.add_cell(nb, "code", None)
            store.update_cell(nb, cell.id, code)
            added["id"] = cell.id

        await self._change(project_id, None, add)
        result = await self._run(project_id, added["id"])
        if result is None:
            return "The cell was deleted before it ran."
        text = outputs_as_text([output_props(o) for o in result.outputs])
        label = {"done": "out", "error": "error", "interrupted": "interrupted", "timeout": "timed out"}[result.status]
        return trim(f"[cell {result.execution_count}] {label}: {text or '(no output)'}", MODEL_OUTPUT_MAX_CHARS)
