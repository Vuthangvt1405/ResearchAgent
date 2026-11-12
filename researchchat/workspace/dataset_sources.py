"""Turn a dataset ref into a file plan, and stream files safely (NB-3 plan §4.1).

Only Hugging Face and Zenodo have a file API. Every URL is built here from
the catalog API, never taken from model text. Downloads are HTTPS only; every
redirect hop and next-page link is re-checked: HTTPS, and every address the
host resolves to must be public (SEC1). Redirects are followed by hand.
"""

import asyncio
import errno
import fnmatch
import hashlib
import ipaddress
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

import httpx

from researchchat.workspace import ErrorCode, WorkspaceError
from researchchat.workspace.datasets_store import NAME_MAX, Source, safe_relpath

CATALOG_HOSTS = {"huggingface": "huggingface.co", "zenodo": "zenodo.org"}
MAX_REDIRECTS = 5
HF_PAGE_SIZE = 1000
USER_AGENT = "ResearchChat"  # generic; no tokens are ever sent (A1, SEC14)
HEADERS = {"User-Agent": USER_AGENT}
AVAILABLE_FILES_MAX = 100
CHUNK_SIZE = 1 << 16
API_TIMEOUT = 30

HF_PART_RE = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
ZENODO_ID_RE = re.compile(r"^[0-9]{1,12}$")
PREFIXES: dict[str, Source] = {"hf": "huggingface", "huggingface": "huggingface", "zenodo": "zenodo"}
REDIRECTS = {301, 302, 303, 307, 308}


@dataclass
class PlannedFile:
    path: str  # safe relative path (datasets_store.safe_relpath)
    size: int  # bytes, from the catalog
    checksum: str | None  # "sha256:…" (HF LFS) / "md5:…" (Zenodo) / None
    url: str  # https download URL built from the catalog API, pinned to the revision


@dataclass
class DatasetPlan:
    source: Source
    source_id: str  # HF repo id / Zenodo record id
    name: str  # HF card pretty_name or repo id; Zenodo title
    revision: str | None  # HF commit sha; None for Zenodo
    url: str  # landing page
    license: str | None
    files: list[PlannedFile]  # after the `files` filter


def _bad_ref(message: str = "Not a dataset ref. Use the `ref` from dataset_search, e.g. hf:org/name or zenodo:123.") -> WorkspaceError:
    return WorkspaceError(ErrorCode.BAD_REF, message)


def _hf_id(owner: str, name: str) -> str:
    for part in (owner, name):
        if not HF_PART_RE.match(part) or part in (".", ".."):
            raise _bad_ref()
    return f"{owner}/{name}"


def parse_ref(ref) -> tuple[Source, str]:
    """'hf:org/name' / 'zenodo:123' / a dataset page URL -> (source, source_id)."""
    if not isinstance(ref, str) or not ref.strip():
        raise _bad_ref("No dataset ref given.")
    ref = ref.strip()
    if "://" in ref:
        parts = urlparse(ref)
        segments = [s for s in parts.path.split("/") if s]
        if parts.scheme != "https" or parts.port is not None or parts.username or parts.password:
            raise _bad_ref()
        host = (parts.hostname or "").removeprefix("www.")
        if host == "huggingface.co" and len(segments) >= 3 and segments[0] == "datasets":
            return "huggingface", _hf_id(segments[1], segments[2])
        if host == "zenodo.org" and len(segments) >= 2 and segments[0] in ("records", "record"):
            if ZENODO_ID_RE.match(segments[1]):
                return "zenodo", segments[1]
        raise _bad_ref()
    prefix, sep, rest = ref.partition(":")
    if not sep:
        raise _bad_ref()
    source = PREFIXES.get(prefix.lower())
    if source is None:
        raise WorkspaceError(
            ErrorCode.UNSUPPORTED_SOURCE,
            f"Downloads work for Hugging Face and Zenodo datasets only, not {prefix[:20]!r}. "
            "Give the user the dataset's page instead.",
        )
    if source == "zenodo":
        if not ZENODO_ID_RE.match(rest):
            raise _bad_ref()
        return "zenodo", rest
    owner, slash, name = rest.partition("/")
    if not slash or "/" in name:
        raise _bad_ref()
    return "huggingface", _hf_id(owner, name)


# ---- URL safety -----------------------------------------------------------------


async def lookup_host(host: str) -> list[str]:
    """Every address `host` resolves to (an IP literal is returned as is)."""
    try:
        return [str(ipaddress.ip_address(host))]
    except ValueError:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None)
        return [info[4][0] for info in infos]


def _blocked(url: str) -> WorkspaceError:
    host = urlparse(url).hostname or "?"
    return WorkspaceError(ErrorCode.DOWNLOAD_FAILED, f"blocked a request to {host[:60]} (only public HTTPS hosts)")


async def check_download_url(url: str, source: Source | None = None, *, catalog_only: bool = False) -> None:
    """HTTPS only and every resolved address public.

    With `source`, the host must be that catalog's host; with `catalog_only`,
    any catalog host (the first hop of a planned file).
    """
    parts = urlparse(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.username or parts.password:
        raise _blocked(url)
    if source is not None and host != CATALOG_HOSTS[source]:
        raise _blocked(url)
    if catalog_only and host not in CATALOG_HOSTS.values():
        raise _blocked(url)
    try:
        addresses = await lookup_host(host)
    except OSError as e:
        raise WorkspaceError(ErrorCode.DOWNLOAD_FAILED, f"couldn't find host {host[:60]}") from e
    if not addresses or not all(ipaddress.ip_address(a.split("%")[0]).is_global for a in addresses):
        raise _blocked(url)


async def open_checked(
    client: httpx.AsyncClient, url: str, *, source: Source | None = None, catalog_only: bool = False
) -> httpx.Response:
    """GET `url` as a stream, following up to MAX_REDIRECTS redirects, checking every hop.

    The first hop must pass the `source` / `catalog_only` host rule; later hops
    (e.g. a CDN) only need to be public HTTPS. The caller closes the response.
    """
    for hop in range(MAX_REDIRECTS + 1):
        if hop == 0:
            await check_download_url(url, source, catalog_only=catalog_only)
        else:
            await check_download_url(url)
        response = await client.send(client.build_request("GET", url, headers=HEADERS), stream=True)
        location = response.headers.get("location")
        if response.status_code in REDIRECTS and location:
            await response.aclose()
            url = urljoin(url, location)
            continue
        return response
    raise WorkspaceError(ErrorCode.DOWNLOAD_FAILED, "too many redirects")


async def _get_json(client: httpx.AsyncClient, url: str, source: Source, missing: tuple[int, ...]) -> httpx.Response:
    try:
        response = await open_checked(client, url, source=source)
        try:
            await response.aread()
        finally:
            await response.aclose()
    except httpx.HTTPError as e:
        raise WorkspaceError(ErrorCode.DOWNLOAD_FAILED, f"the {source} catalog didn't answer") from e
    if response.status_code in missing:
        raise WorkspaceError(ErrorCode.NOT_FOUND, "Dataset not found (or it's private).")
    if response.status_code != 200:
        raise WorkspaceError(ErrorCode.DOWNLOAD_FAILED, f"the {source} catalog answered HTTP {response.status_code}")
    return response


def _clean(text, limit: int = NAME_MAX) -> str | None:
    """Catalog text for display: control characters removed, length capped (SEC20)."""
    if text is None:
        return None
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(text)).strip()
    return text[:limit] or None


# ---- file selection --------------------------------------------------------------


def match_files(names: list[str], patterns: list[str] | None) -> list[str]:
    """Names matching any glob pattern (on the full path or the file name); all names when patterns is None."""
    if patterns is None:
        return list(names)
    return [
        n for n in names
        if any(fnmatch.fnmatchcase(n, p) or fnmatch.fnmatchcase(n.rsplit("/", 1)[-1], p) for p in patterns)
    ]


def _no_files(names: list[str]) -> WorkspaceError:
    return WorkspaceError(
        ErrorCode.NO_FILES,
        "No files match that selection." if names else "This dataset has no downloadable files.",
        {"available_files": names[:AVAILABLE_FILES_MAX]},
    )


def _too_many(max_files: int) -> WorkspaceError:
    return WorkspaceError(
        ErrorCode.TOO_MANY_FILES,
        f"More than {max_files} files. Pass `files` (names or patterns like \"*.csv\") to pick fewer.",
        {"max_files": max_files},
    )


# ---- resolvers ---------------------------------------------------------------------


def file_url(source: Source, source_id: str, revision: str | None, path: str) -> str:
    """The download URL of one file, built from catalog ids only (never from model text)."""
    if source == "huggingface":
        return f"https://huggingface.co/datasets/{source_id}/resolve/{revision}/{quote(path)}"
    return f"https://zenodo.org/api/records/{source_id}/files/{quote(path)}/content"


async def resolve(
    source: Source,
    source_id: str,
    files: list[str] | None = None,
    *,
    max_files: int,
    revision: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> DatasetPlan:
    """Ask the catalog for the file list, filtered by `files` globs.

    `revision` pins a Hugging Face commit (an existing dataset keeps its
    version, AC12); None means the current revision. Zenodo records never change.
    """
    resolver = resolve_huggingface if source == "huggingface" else resolve_zenodo
    if client is not None:
        return await resolver(source_id, files, max_files=max_files, revision=revision, client=client)
    async with httpx.AsyncClient(timeout=API_TIMEOUT) as own:
        return await resolver(source_id, files, max_files=max_files, revision=revision, client=own)


def _hf_license(info: dict) -> str | None:
    card = info.get("cardData") or {}
    value = card.get("license")
    if isinstance(value, list):
        value = value[0] if value else None
    if not value:
        value = next((t.split(":", 1)[1] for t in info.get("tags") or [] if t.startswith("license:")), None)
    return _clean(value, 60)


async def resolve_huggingface(
    repo_id: str, files: list[str] | None, *, max_files: int, client: httpx.AsyncClient, revision: str | None = None
) -> DatasetPlan:
    """/api/datasets/{id} (gated, private, sha, pretty_name) + tree pages, early stop at max_files."""
    landing = f"https://huggingface.co/datasets/{repo_id}"
    response = await _get_json(client, f"https://huggingface.co/api/datasets/{repo_id}", "huggingface", (401, 403, 404))
    info = response.json()
    if info.get("private") or info.get("gated"):
        raise WorkspaceError(
            ErrorCode.NOT_PUBLIC,
            f"This dataset needs a login or accepting its terms. Give the user the page: {landing}",
            {"url": landing},
        )
    sha = str(revision or info.get("sha") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise WorkspaceError(ErrorCode.DOWNLOAD_FAILED, "the catalog gave no revision")

    names: list[str] = []
    planned: list[PlannedFile] = []
    url: str | None = f"https://huggingface.co/api/datasets/{repo_id}/tree/{sha}?recursive=true"
    while url:
        page = await _get_json(client, url, "huggingface", (404,))
        for entry in page.json():
            if entry.get("type") != "file" or entry.get("path") == ".gitattributes":
                continue
            names.append(str(entry.get("path")))
            if not match_files([names[-1]], files):
                continue
            path = safe_relpath(entry.get("path"))
            lfs = entry.get("lfs") or {}
            oid = str(lfs.get("oid") or "")
            planned.append(
                PlannedFile(
                    path=path,
                    size=int(lfs.get("size") or entry.get("size") or 0),
                    checksum=f"sha256:{oid}" if re.fullmatch(r"[0-9a-f]{64}", oid) else None,
                    url=file_url("huggingface", repo_id, sha, path),
                )
            )
            if len(planned) > max_files:
                raise _too_many(max_files)
        next_url = page.links.get("next", {}).get("url")
        if next_url:
            next_url = urljoin(url, next_url)
            parts = urlparse(next_url)
            if parts.scheme != "https" or parts.hostname != CATALOG_HOSTS["huggingface"]:
                raise _blocked(next_url)
        url = next_url
    if not planned:
        raise _no_files(names)
    card = info.get("cardData") or {}
    return DatasetPlan(
        source="huggingface",
        source_id=repo_id,
        name=_clean(card.get("pretty_name")) or repo_id,
        revision=sha,
        url=landing,
        license=_hf_license(info),
        files=planned,
    )


async def resolve_zenodo(
    record_id: str, files: list[str] | None, *, max_files: int, client: httpx.AsyncClient, revision: str | None = None
) -> DatasetPlan:
    """/api/records/{id}: access_right, files[] with key, size, md5 checksum."""
    response = await _get_json(client, f"https://zenodo.org/api/records/{record_id}", "zenodo", (404, 410))
    data = response.json()
    meta = data.get("metadata") or {}
    landing = (data.get("links") or {}).get("self_html") or f"https://zenodo.org/records/{record_id}"
    if not str(landing).startswith("https://zenodo.org/"):
        landing = f"https://zenodo.org/records/{record_id}"
    if meta.get("access_right") != "open":
        raise WorkspaceError(
            ErrorCode.NOT_PUBLIC,
            f"This record's files aren't open. Give the user the page: {landing}",
            {"url": landing},
        )
    entries = data.get("files") or []
    names = [str(f.get("key")) for f in entries]
    planned = []
    for entry in entries:
        if not match_files([str(entry.get("key"))], files):
            continue
        path = safe_relpath(entry.get("key"))
        checksum = str(entry.get("checksum") or "")
        planned.append(
            PlannedFile(
                path=path,
                size=int(entry.get("size") or 0),
                checksum=checksum if re.fullmatch(r"md5:[0-9a-f]{32}", checksum) else None,
                url=file_url("zenodo", record_id, None, path),
            )
        )
        if len(planned) > max_files:
            raise _too_many(max_files)
    if not planned:
        raise _no_files(names)
    return DatasetPlan(
        source="zenodo",
        source_id=record_id,
        name=_clean(meta.get("title")) or f"Zenodo record {record_id}",
        revision=None,
        url=landing,
        license=_clean((meta.get("license") or {}).get("id"), 60),
        files=planned,
    )


# ---- download ------------------------------------------------------------------------


def _failed(reason: str) -> WorkspaceError:
    return WorkspaceError(ErrorCode.DOWNLOAD_FAILED, reason)


async def stream_file(
    file: PlannedFile,
    dest: Path,
    *,
    client: httpx.AsyncClient,
    on_bytes: Callable[[int], Awaitable[None]],
    stall_timeout: float,
) -> None:
    """Download one file to `dest`, following redirects by hand (each hop checked).

    Aborts past the declared size, on a stall, or on a write error; verifies
    size and checksum. Raises WorkspaceError(DOWNLOAD_FAILED, reason).
    `on_bytes` may raise to stop the download (disk full, cancel).
    """
    algo, _, expected = (file.checksum or "").partition(":")
    hasher = hashlib.new(algo) if algo in ("md5", "sha256") else None
    try:
        response = await asyncio.wait_for(open_checked(client, file.url, catalog_only=True), stall_timeout)
    except asyncio.TimeoutError as e:
        raise _failed(f"stalled on {file.path}") from e
    except httpx.HTTPError as e:
        raise _failed(f"network error on {file.path}") from e
    try:
        if response.status_code != 200:
            raise _failed(f"HTTP {response.status_code} on {file.path}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        received = 0
        chunks = response.aiter_bytes(CHUNK_SIZE)
        with open(dest, "wb") as out:
            while True:
                try:
                    chunk = await asyncio.wait_for(anext(chunks), stall_timeout)
                except StopAsyncIteration:
                    break
                received += len(chunk)
                if received > file.size:
                    raise _failed(f"{file.path} is bigger than the catalog said")
                if hasher:
                    hasher.update(chunk)
                try:
                    out.write(chunk)
                except OSError as e:
                    if e.errno == errno.ENOSPC:
                        raise _failed("disk full") from e
                    raise _failed(f"couldn't write {file.path}") from e
                await on_bytes(len(chunk))
    except asyncio.TimeoutError as e:
        raise _failed(f"stalled on {file.path}") from e
    except httpx.HTTPError as e:
        raise _failed(f"network error on {file.path}") from e
    finally:
        await response.aclose()
    if received != file.size:
        raise _failed(f"{file.path} is incomplete")
    if hasher and hasher.hexdigest() != expected:
        raise _failed(f"checksum mismatch on {file.path}")
