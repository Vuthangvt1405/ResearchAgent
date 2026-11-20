"""A one-shot listener on 127.0.0.1 that catches Kaggle's redirect back after the user approves.

It runs only while a sign-in is waiting, on a free port, and never logs request
paths (they carry the one-time code).
"""

import asyncio
import contextlib
import urllib.parse
from dataclasses import dataclass, field
from typing import Literal

CALLBACK_PATH = "/callback"
LOOPBACK_HOST = "127.0.0.1"
REDIRECT_HOST = "localhost"  # the redirect form Kaggle accepted when tried live
CONNECTED_PAGE = "Connected. You can close this tab and go back to ResearchChat."
CANCELLED_PAGE = "Sign-in cancelled. You can close this tab."
MAX_REQUEST_LINE_BYTES = 8192
READ_TIMEOUT_SECONDS = 5

CallbackOutcome = Literal["code", "cancelled", "timed_out"]


@dataclass(frozen=True)
class CallbackResult:
    """How the browser hand-off ended; `code` is set only when the user approved."""

    outcome: CallbackOutcome
    code: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class BrowserReply:
    status: int
    text: str


NOT_OURS = BrowserReply(404, "")


class CallbackListener:
    """Waits for exactly one callback that carries the expected state."""

    def __init__(self, expected_state: str, timeout_seconds: float):
        self.expected_state = expected_state
        self.timeout_seconds = timeout_seconds
        self._server: asyncio.Server | None = None
        self._result: asyncio.Future[CallbackResult] | None = None

    async def start(self) -> str:
        self._result = asyncio.get_running_loop().create_future()
        self._server = await asyncio.start_server(self._serve, host=LOOPBACK_HOST, port=0)
        port = self._server.sockets[0].getsockname()[1]
        return f"http://{REDIRECT_HOST}:{port}{CALLBACK_PATH}"

    async def wait(self) -> CallbackResult:
        if self._result is None:
            raise RuntimeError("start() first")
        try:
            return await asyncio.wait_for(asyncio.shield(self._result), self.timeout_seconds)
        except TimeoutError:
            return CallbackResult("timed_out")
        finally:
            await self.close()

    async def close(self) -> None:
        if self._result is not None and not self._result.done():
            self._result.set_result(CallbackResult("cancelled"))
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
            self._server = None

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_target = await _read_request_target(reader)
            reply = self._answer(request_target) if request_target else NOT_OURS
            await _write_reply(writer, reply)
        except (OSError, asyncio.IncompleteReadError, TimeoutError, ValueError):
            pass  # a broken or slow request is just ignored; the listener keeps waiting
        finally:
            writer.close()

    def _answer(self, request_target: str) -> BrowserReply:
        parts = urllib.parse.urlsplit(request_target)
        params = dict(urllib.parse.parse_qsl(parts.query))
        is_ours = parts.path == CALLBACK_PATH and params.get("state") == self.expected_state
        if not is_ours or self._result is None or self._result.done():
            return NOT_OURS
        if params.get("code"):
            self._result.set_result(CallbackResult("code", params["code"]))
            return BrowserReply(200, CONNECTED_PAGE)
        self._result.set_result(CallbackResult("cancelled"))
        return BrowserReply(200, CANCELLED_PAGE)


async def _read_request_target(reader: asyncio.StreamReader) -> str | None:
    """The path and query of a GET request line, or None for anything else."""
    line = await asyncio.wait_for(reader.readline(), READ_TIMEOUT_SECONDS)
    if len(line) > MAX_REQUEST_LINE_BYTES:
        return None
    words = line.decode("latin-1").split()
    if len(words) != 3 or words[0] != "GET":
        return None
    return words[1]


async def _write_reply(writer: asyncio.StreamWriter, reply: BrowserReply) -> None:
    body = reply.text.encode("utf-8")
    reason = "OK" if reply.status == 200 else "Not Found"
    head = (
        f"HTTP/1.1 {reply.status} {reason}\r\nContent-Type: text/plain; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n"
    )
    writer.write(head.encode("ascii") + body)
    await writer.drain()
