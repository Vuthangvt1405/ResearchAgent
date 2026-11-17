"""Download one data file from a link the user pasted into the chat.

A link has no catalog behind it: no file list, no declared licence, often no
size. The user is the only one who may supply the address, so a link is
accepted only when it appears word for word in one of the user's own chat
messages; links from tool results, notes or the assistant's replies never
count. Every hop keeps the HTTPS-and-public-address rule of `sources`.
"""

import asyncio
import errno
import logging
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping
from pathlib import Path
from typing import BinaryIO
from urllib.parse import ParseResult, unquote, urlparse, urlunparse

import httpx

from researchchat.workspace import ErrorCode, WorkspaceError
from researchchat.workspace.datasets import sources
from researchchat.workspace.datasets.sources import CHUNK_SIZE, DatasetPlan, PlannedFile
from researchchat.workspace.datasets.store import Source, safe_relpath

LINK_SOURCE: Source = "link"
LINK_MAX_CHARS = 2000
LINK_PROBE_TIMEOUT_SECONDS = 15  # the probe runs while other requests wait for the queue lock
FALLBACK_FILE_NAME = "download"  # a link whose path ends in "/" has no file name
WEB_PAGE_SNIFF_BYTES = 512  # enough to see "<!doctype html" after leading whitespace
WEB_PAGE_CONTENT_TYPES = ("text/html", "application/xhtml+xml")
WEB_PAGE_STARTS = (b"<!doctype html", b"<html")
TRAILING_PUNCTUATION = ".,;:!?)]>\"'"  # a link at the end of a sentence
LINK_HEADERS = {**sources.HEADERS, "Accept-Encoding": "identity"}  # the size the site states is the size written
LINK_RE = re.compile(r"https://[^\s<>\"'`]+")
NOT_FOUND_STATUSES = (404, 410)
LOGIN_STATUSES = (401, 403)

NOT_PASTED_MESSAGE = (
    "Only links the user pasted can be downloaded. "
    "Show the user the link and ask them to paste it if they want it."
)
NOT_A_FILE_MESSAGE = "This link opens a web page, not a data file. Paste the link to the file itself."
ONE_FILE_MESSAGE = "`files` and `update` don't apply to a file link: a link is one file."
HTTPS_ONLY_MESSAGE = "Only https links can be downloaded."
HTTP_LOGGER = "httpx"  # logs every request URL at INFO


class HideQueryStrings(logging.Filter):
    """Drop the query of URLs in httpx's request log: a pasted link may carry a signed token there."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(_without_query(arg) for arg in record.args)
        return True


def _without_query(arg: object) -> object:
    if isinstance(arg, httpx.URL) and arg.query:
        return arg.copy_with(query=None)
    return arg


def hide_query_strings_in_http_log() -> None:
    """Install HideQueryStrings once on the httpx logger."""
    http_log = logging.getLogger(HTTP_LOGGER)
    if not any(isinstance(f, HideQueryStrings) for f in http_log.filters):
        http_log.addFilter(HideQueryStrings())


# Installed on import, so no entry point can forget it. It applies to every httpx request log in the
# app (catalog and model calls too): those lose only their query strings, which nothing reads there.
hide_query_strings_in_http_log()


# ---- which links count ----------------------------------------------------------


def find_pasted_links(history: Iterable[Mapping[str, object]]) -> frozenset[str]:
    """Every whole https:// link in the user's own messages, trailing punctuation trimmed."""
    links: set[str] = set()
    for message in history:
        content = message.get("content")
        if message.get("role") != "user" or not isinstance(content, str):
            continue
        for token in LINK_RE.findall(content):
            link = _normalized_or_none(token.rstrip(TRAILING_PUNCTUATION))
            if link is not None:
                links.add(link)
    return frozenset(links)


def _normalized_or_none(link: str) -> str | None:
    try:
        return normalize_link(link)
    except WorkspaceError:
        return None


def normalize_link(link: str) -> str:
    """The link as it is fetched and compared: fragment removed; BAD_REF when not a usable https link."""
    if len(link) > LINK_MAX_CHARS:
        raise WorkspaceError(ErrorCode.BAD_REF, f"The link is longer than {LINK_MAX_CHARS} characters.")
    parts = urlparse(link)
    if parts.scheme != "https":
        raise WorkspaceError(ErrorCode.BAD_REF, HTTPS_ONLY_MESSAGE)
    has_credentials = bool(parts.username or parts.password)
    if not parts.hostname or has_credentials or _has_port(parts):
        raise WorkspaceError(ErrorCode.BAD_REF, "Not a usable file link. Paste the https link to the file.")
    return urlunparse(parts._replace(fragment=""))


def _has_port(parts: ParseResult) -> bool:
    try:
        return parts.port is not None
    except ValueError:
        return True  # a port that isn't a number


def parse_dataset_ref(ref: object) -> tuple[Source, str]:
    """A catalog ref or dataset page as `sources.parse_ref` reads it; any other https URL is a file link."""
    try:
        return sources.parse_ref(ref)
    except WorkspaceError as e:
        is_url = isinstance(ref, str) and "://" in ref
        if e.code != ErrorCode.BAD_REF or not is_url:
            raise
    return LINK_SOURCE, normalize_link(ref.strip())


def require_pasted(link: str, pasted_links: frozenset[str]) -> None:
    """NOT_PASTED unless `link` is exactly one of the links the user pasted."""
    if link not in pasted_links:
        raise WorkspaceError(ErrorCode.NOT_PASTED, NOT_PASTED_MESSAGE)


def refuse_file_options(files: list[str] | None, update: bool) -> None:
    """A link is one file at one address: no file patterns, no newer version."""
    if files is not None or update:
        raise WorkspaceError(ErrorCode.BAD_REF, ONE_FILE_MESSAGE)


def download_url(source: Source, source_id: str, revision: str | None, path: str) -> str:
    """Where a file of a pool entry is downloaded from: the pasted URL for a link, else the catalog URL."""
    if source == LINK_SOURCE:
        return source_id
    return sources.file_url(source, source_id, revision, path)


# ---- names ----------------------------------------------------------------------


def link_file_name(link: str) -> str:
    """The file name from the link's last path segment, percent-decoded and made safe."""
    file_name = unquote(urlparse(link).path.rsplit("/", 1)[-1]).strip()
    return safe_relpath(file_name or FALLBACK_FILE_NAME)


def host_of(link: str) -> str:
    """The website a link points at, for labels and logs (never the path or query, which may hold secrets)."""
    return (urlparse(link).hostname or "?")[:60]


# ---- web page or file -----------------------------------------------------------


def looks_like_web_page(content_type: str | None, first_bytes: bytes) -> bool:
    """True when the website says HTML, or the body starts like an HTML page."""
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    if media_type in WEB_PAGE_CONTENT_TYPES:
        return True
    return first_bytes.lstrip().lower().startswith(WEB_PAGE_STARTS)


async def _first_chunk(chunks: AsyncIterator[bytes]) -> bytes:
    try:
        return await anext(chunks)
    except StopAsyncIteration:
        return b""


def _declared_size(response: httpx.Response) -> int | None:
    value = response.headers.get("content-length", "")
    return int(value) if value.isdigit() else None


def _refuse_unusable_status(status: int) -> None:
    if status in NOT_FOUND_STATUSES:
        raise WorkspaceError(ErrorCode.NOT_FOUND, f"The link is broken (HTTP {status}).")
    if status in LOGIN_STATUSES:
        raise WorkspaceError(ErrorCode.NOT_PUBLIC, "This file needs a login, which isn't supported.")
    if status != 200:
        raise WorkspaceError(ErrorCode.DOWNLOAD_FAILED, f"the website answered HTTP {status}")


# ---- probe ----------------------------------------------------------------------


async def resolve_link(link: str, *, client: httpx.AsyncClient) -> DatasetPlan:
    """Probe the link without downloading it and describe the one file it holds.

    Failures here are reported in the tool call with no card saved: not
    https, private address, 404/410, 401/403, a web page.
    """
    try:
        return await asyncio.wait_for(_probe(link, client), LINK_PROBE_TIMEOUT_SECONDS)
    except TimeoutError as e:
        raise WorkspaceError(ErrorCode.DOWNLOAD_FAILED, "the website didn't answer") from e
    except httpx.HTTPError as e:
        raise WorkspaceError(ErrorCode.DOWNLOAD_FAILED, f"couldn't reach {host_of(link)}") from e


async def _probe(link: str, client: httpx.AsyncClient) -> DatasetPlan:
    response = await sources.open_checked(client, link, headers=LINK_HEADERS)
    try:
        _refuse_unusable_status(response.status_code)
        first_bytes = await _first_chunk(response.aiter_bytes(WEB_PAGE_SNIFF_BYTES))
        if looks_like_web_page(response.headers.get("content-type"), first_bytes):
            raise WorkspaceError(ErrorCode.NOT_A_FILE, NOT_A_FILE_MESSAGE)
        declared_size = _declared_size(response)
    finally:
        await response.aclose()
    return _plan_for(link, declared_size)


def _plan_for(link: str, declared_size: int | None) -> DatasetPlan:
    file_name = link_file_name(link)
    planned = PlannedFile(
        path=file_name,
        size=declared_size or 0,
        checksum=None,
        url=link,
        size_is_known=declared_size is not None,
    )
    # A fresh revision per download: each project gets its own copy until reuse checks the file is unchanged.
    return DatasetPlan(
        source=LINK_SOURCE,
        source_id=link,
        name=file_name,
        revision=uuid.uuid4().hex,
        url=link,
        license=None,
        files=[planned],
    )


# ---- download -------------------------------------------------------------------


def _failed(reason: str) -> WorkspaceError:
    return WorkspaceError(ErrorCode.DOWNLOAD_FAILED, reason)


async def stream_link_file(
    file: PlannedFile,
    dest: Path,
    *,
    client: httpx.AsyncClient,
    on_bytes: Callable[[int], Awaitable[None]],
    stall_timeout: float,
) -> int:
    """Download a pasted-link file to `dest`; returns the number of bytes written.

    Re-checks every hop, refuses a body that turned into a web page, and
    checks the size only when the website declared one.
    """
    try:
        response = await asyncio.wait_for(sources.open_checked(client, file.url, headers=LINK_HEADERS), stall_timeout)
    except TimeoutError as e:
        raise _failed(f"stalled on {file.path}") from e
    except httpx.HTTPError as e:
        raise _failed(f"network error on {file.path}") from e
    try:
        if response.status_code != 200:
            raise _failed(f"HTTP {response.status_code} on {file.path}")
        received = await _write_body(file, response, dest, on_bytes, stall_timeout)
    except TimeoutError as e:
        raise _failed(f"stalled on {file.path}") from e
    except httpx.HTTPError as e:
        raise _failed(f"network error on {file.path}") from e
    finally:
        await response.aclose()
    if file.size_is_known and received != file.size:
        raise _failed(f"{file.path} is incomplete")
    return received


async def _write_body(
    file: PlannedFile,
    response: httpx.Response,
    dest: Path,
    on_bytes: Callable[[int], Awaitable[None]],
    stall_timeout: float,
) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    chunks = response.aiter_bytes(CHUNK_SIZE)
    received = 0
    with open(dest, "wb") as out:  # noqa: ASYNC230 - same local-disk write as sources.stream_file
        while True:
            try:
                chunk = await asyncio.wait_for(anext(chunks), stall_timeout)
            except StopAsyncIteration:
                break
            if received == 0 and looks_like_web_page(response.headers.get("content-type"), chunk):
                raise _failed("the link now opens a web page")
            received += len(chunk)
            if file.size_is_known and received > file.size:
                raise _failed(f"{file.path} is bigger than the website said")
            _write_chunk(out, chunk, file.path)
            await on_bytes(len(chunk))
    return received


def _write_chunk(out: BinaryIO, chunk: bytes, path: str) -> None:
    try:
        out.write(chunk)
    except OSError as e:
        if e.errno == errno.ENOSPC:
            raise _failed("disk full") from e
        raise _failed(f"couldn't write {path}") from e
