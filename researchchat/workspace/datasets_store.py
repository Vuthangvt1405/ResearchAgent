"""Datasets of a project on disk (NB-3 plan §3.3).

workspaces/<project_id>/
    datasets.json              {"format": 1, "datasets": [DatasetRecord, ...]}
    files/datasets/<id>/       downloaded, verified files (seen by the kernel at /work/datasets/<id>/)
    .dataset-partial/<id>/     files still downloading (invisible to the kernel)
    .dataset-partial/<id>.new/ a new revision being staged (update: true)
    .dataset-partial/<id>.old/ the old folder during the update swap

datasets.json sits next to files/, not in it, so kernel code can't edit it.
This module only reads and writes disk: no locks, no network. The rules
(who may delete, when to download) live in dataset_service.py.

Plan: docs/plans/NB-3-dataset-download-plan.md
"""

import json
import os
import re
import shutil
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

from researchchat.config import WORKSPACES_DIR
from researchchat.workspace import ErrorCode, WorkspaceError
from researchchat.workspace import store

MANIFEST_FILE = "datasets.json"
MANIFEST_FORMAT = 1
DATASETS_DIR = "datasets"  # under the project's files/
PARTIAL_DIR = ".dataset-partial"
DATASET_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
DATASET_ID_MAX = 80
NAME_MAX = 200
PATH_MAX = 1024
KERNEL_ROOT = "/work/datasets"  # how the kernel sees files/datasets/
PARTIAL_SUFFIXES = ("", ".new", ".old")
DRIVE_RE = re.compile(r"^[A-Za-z]:")

Source = Literal["huggingface", "zenodo"]
StoredStatus = Literal["queued", "downloading", "ready", "failed"]
DatasetStatus = Literal["queued", "downloading", "ready", "failed", "missing"]  # missing is computed on read


@dataclass
class DatasetFile:
    path: str  # relative to the dataset folder; checked by safe_relpath
    size: int  # bytes, as the catalog declared it
    checksum: str | None  # "md5:…" / "sha256:…", or None when the catalog gives none
    ready: bool = False  # downloaded, verified and moved into files/datasets/<id>/


@dataclass
class DatasetRecord:
    id: str  # generated slug, folder name under files/datasets/; never from model text
    name: str  # title for people (≤ 200 chars)
    source: Source  # which catalog
    source_id: str  # stable key in that catalog (HF repo id, Zenodo record id)
    revision: str | None  # HF commit hash; None for Zenodo (records are versioned by id)
    url: str | None  # landing page
    license: str | None  # shown while downloading and in the details
    selection: list[str] | None  # every `files` pattern asked for so far; None = all files
    status: StoredStatus
    files: list[DatasetFile] = field(default_factory=list)
    requested_at: str = ""  # ISO 8601 UTC; queue order
    downloaded_at: str | None = None  # ISO 8601 UTC
    error: str | None = None  # one-line reason when failed

    @property
    def size_bytes(self) -> int:
        """Derived from files[] (plan §3.3)."""
        return sum(f.size for f in self.files)


# ---- manifest -----------------------------------------------------------------


def manifest_path(project_id: str, root: Path = WORKSPACES_DIR) -> Path:
    """workspaces/<project>/datasets.json, inside the project folder."""
    return store.project_dir(project_id, root) / MANIFEST_FILE


def _record_from_dict(d: dict) -> DatasetRecord:
    files = [
        DatasetFile(str(f["path"]), int(f["size"]), f.get("checksum"), bool(f.get("ready", False)))
        for f in d.get("files") or []
    ]
    record = DatasetRecord(
        id=str(d["id"]),
        name=str(d.get("name") or d["id"])[:NAME_MAX],
        source=d["source"],
        source_id=str(d["source_id"]),
        revision=d.get("revision"),
        url=d.get("url"),
        license=d.get("license"),
        selection=list(d["selection"]) if d.get("selection") is not None else None,
        status=d.get("status", "failed"),
        files=files,
        requested_at=str(d.get("requested_at") or ""),
        downloaded_at=d.get("downloaded_at"),
        error=d.get("error"),
    )
    if not DATASET_ID_RE.match(record.id) or record.source not in ("huggingface", "zenodo"):
        raise ValueError("bad record")
    if record.status not in ("queued", "downloading", "ready", "failed"):
        raise ValueError("bad status")
    return record


def load_records(project_id: str, root: Path = WORKSPACES_DIR) -> list[DatasetRecord]:
    """Read datasets.json; missing = []. A corrupt file is renamed .bad and read as [] (A6)."""
    path = manifest_path(project_id, root)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("format") != MANIFEST_FORMAT:
            raise ValueError("unknown format")
        return [_record_from_dict(d) for d in data.get("datasets") or []]
    except (ValueError, KeyError, TypeError, AttributeError):
        os.replace(path, path.with_name(MANIFEST_FILE + ".bad"))
        return []


def save_records(project_id: str, records: list[DatasetRecord], root: Path = WORKSPACES_DIR) -> None:
    """Write datasets.json atomically (temp file + os.replace, like store.save_notebook)."""
    path = manifest_path(project_id, root)
    data = {"format": MANIFEST_FORMAT, "datasets": [asdict(r) for r in records]}
    tmp = path.with_name(MANIFEST_FILE + ".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def find_record(records: list[DatasetRecord], dataset_id: str) -> DatasetRecord | None:
    """The record with this id among this project's records."""
    return next((r for r in records if r.id == dataset_id), None)


# ---- ids and paths ------------------------------------------------------------


def _slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def make_id(source: Source, source_id: str, existing: list[DatasetRecord]) -> str:
    """hf-<owner>--<name> / zenodo-<id>; -2, -3… on a clash; same (source, source_id) keeps its id."""
    for r in existing:
        if r.source == source and r.source_id == source_id:
            return r.id
    prefix = "hf" if source == "huggingface" else source
    body = "--".join(p for p in (_slug(part) for part in source_id.split("/")) if p) or "dataset"
    base = re.sub(r"-{3,}", "--", f"{prefix}-{body}")[:DATASET_ID_MAX].strip("-")
    taken = {r.id for r in existing}
    candidate, n = base, 2
    while candidate in taken:
        suffix = f"-{n}"
        candidate = base[: DATASET_ID_MAX - len(suffix)].rstrip("-") + suffix
        n += 1
    return candidate


def safe_relpath(name) -> str:
    """A catalog file name as a safe relative POSIX path; WorkspaceError if unsafe."""
    bad = WorkspaceError(ErrorCode.BAD_PAYLOAD, f"Unsafe file name in the dataset: {str(name)[:80]!r}")
    if not isinstance(name, str) or not name.strip() or len(name) > PATH_MAX:
        raise bad
    if "\\" in name or "\x00" in name or name.startswith("/") or DRIVE_RE.match(name):
        raise bad
    parts = [p for p in PurePosixPath(name).parts if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        raise bad
    return "/".join(parts)


def _inside(base: Path, name: str) -> Path:
    """base/name, resolved; must be a direct child of the resolved base."""
    base = base.resolve()
    folder = (base / name).resolve()
    if folder.parent != base:
        raise WorkspaceError(ErrorCode.NOT_FOUND, "Unknown dataset.")
    return folder


def _check_id(dataset_id) -> None:
    if not isinstance(dataset_id, str) or not DATASET_ID_RE.match(dataset_id):
        raise WorkspaceError(ErrorCode.NOT_FOUND, "Unknown dataset.")


def _linked() -> WorkspaceError:
    return WorkspaceError(ErrorCode.DOWNLOAD_FAILED, "the dataset folder is a link, so it wasn't used")


def datasets_root(project_id: str, root: Path = WORKSPACES_DIR) -> Path:
    """files/datasets/. Kernel code can replace it with a symlink (files/ is /work,
    read-write), so it's never resolved through: a link here is refused (SEC2, SEC8)."""
    base = (store.project_dir(project_id, root) / store.FILES_DIR).resolve() / DATASETS_DIR
    if base.resolve() != base:
        raise _linked()
    return base


def dataset_dir(project_id: str, dataset_id: str, root: Path = WORKSPACES_DIR) -> Path:
    """files/datasets/<id>/; refused when it or files/datasets is a link."""
    _check_id(dataset_id)
    folder = datasets_root(project_id, root) / dataset_id
    if folder.resolve() != folder:
        raise _linked()
    return folder


def partial_root(project_id: str, root: Path = WORKSPACES_DIR) -> Path:
    return store.project_dir(project_id, root) / PARTIAL_DIR


def partial_dir(project_id: str, dataset_id: str, suffix: str = "", root: Path = WORKSPACES_DIR) -> Path:
    """.dataset-partial/<id>[.new|.old]/, checked to resolve inside the project folder."""
    _check_id(dataset_id)
    if suffix not in PARTIAL_SUFFIXES:
        raise ValueError(f"bad partial suffix {suffix!r}")
    return _inside(partial_root(project_id, root), dataset_id + suffix)


def file_path(project_id: str, dataset_id: str, relpath: str, root: Path = WORKSPACES_DIR, folder: Path | None = None) -> Path:
    """One dataset file on disk (in `folder`, default dataset_dir); must stay under it after resolve()."""
    base = (folder or dataset_dir(project_id, dataset_id, root)).resolve()
    path = (base / safe_relpath(relpath)).resolve()
    if path == base or not path.is_relative_to(base):
        raise WorkspaceError(ErrorCode.BAD_PAYLOAD, "Unsafe file name in the dataset.")
    return path


def kernel_path(dataset_id: str, relpath: str = "") -> str:
    """/work/datasets/<id>/<relpath>: the path the model and the kernel use."""
    return f"{KERNEL_ROOT}/{dataset_id}" + (f"/{relpath}" if relpath else "")


# ---- disk state ---------------------------------------------------------------


def missing_files(project_id: str, record: DatasetRecord, root: Path = WORKSPACES_DIR) -> list[str]:
    """Ready files that are gone from disk or whose size changed (A14)."""
    missing = []
    for f in record.files:
        if not f.ready:
            continue
        try:
            path = file_path(project_id, record.id, f.path, root)
            ok = path.is_file() and path.stat().st_size == f.size
        except (WorkspaceError, OSError):
            ok = False
        if not ok:
            missing.append(f.path)
    return missing


def _rmtree(path: Path) -> None:
    """Remove a folder (or a symlink in its place) without following links."""
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def remove_dataset_dir(project_id: str, dataset_id: str, root: Path = WORKSPACES_DIR) -> None:
    """Delete files/datasets/<id>/ only; record file paths are ignored.

    Links are never followed: a linked <id> is unlinked, and when files/datasets
    itself is a link nothing is touched (none of it is ours).
    """
    _check_id(dataset_id)
    try:
        base = datasets_root(project_id, root)
    except WorkspaceError:
        return
    _rmtree(base / dataset_id)


def remove_partial(project_id: str, dataset_id: str, root: Path = WORKSPACES_DIR) -> None:
    """Delete .dataset-partial/<id>/ and <id>.new/ (a failed or cancelled job, A16)."""
    for suffix in ("", ".new"):
        _rmtree(partial_dir(project_id, dataset_id, suffix, root))
    try:
        partial_root(project_id, root).rmdir()  # only when empty
    except OSError:
        pass


def swap_in_update(project_id: str, dataset_id: str, root: Path = WORKSPACES_DIR) -> None:
    """Move the old folder to <id>.old, <id>.new into place, then delete <id>.old (A15)."""
    final = dataset_dir(project_id, dataset_id, root)
    new = partial_dir(project_id, dataset_id, ".new", root)
    old = partial_dir(project_id, dataset_id, ".old", root)
    _rmtree(old)
    final.parent.mkdir(parents=True, exist_ok=True)
    if final.exists():
        os.replace(final, old)
    os.replace(new, final)
    _rmtree(old)


def recover_partials(project_id: str, root: Path = WORKSPACES_DIR) -> None:
    """At startup: restore <id>.old if the final folder is missing, then clear .dataset-partial/."""
    base = partial_root(project_id, root)
    if not base.is_dir():
        return
    for entry in base.iterdir():
        name = entry.name
        if name.endswith(".old") and DATASET_ID_RE.match(name[:-4]) and not entry.is_symlink():
            final = dataset_dir(project_id, name[:-4], root)
            if not final.exists():
                final.parent.mkdir(parents=True, exist_ok=True)
                os.replace(entry, final)
    _rmtree(base)
