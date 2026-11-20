"""The FastAPI app: the chat page, its files and the chat socket."""

import asyncio
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, Request, Response, WebSocket
from fastapi.responses import FileResponse, PlainTextResponse

from researchchat.chat_start import switches_for
from researchchat.server.guard import is_allowed_host
from researchchat.server.socket import ChatSessions, serve_chat
from researchchat.workspace import actions

# The page may only run its own scripts and talk to this server
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)


@dataclass(frozen=True)
class ServerSettings:
    port: int
    page_dir: Path  # the built page; empty until the page exists


NO_PAGE_YET = "The SillyTherin page isn't built yet."
_background: set[asyncio.Task[None]] = set()  # keeps the start-up cleanups alive until they finish


async def run_startup_cleanup() -> None:
    """Remove kernel containers and cut-off downloads left by an earlier run, without delaying start-up."""
    for cleanup in (actions.kernels.cleanup_leftovers(), actions.datasets.startup_cleanup()):
        task = asyncio.create_task(cleanup)
        _background.add(task)
        task.add_done_callback(_background.discard)


async def stop_kernels() -> None:
    # Kernels hold memory until stopped; without this they run on after the app exits
    try:
        await actions.kernels.stop_all()
    except (OSError, subprocess.TimeoutExpired):
        pass  # Docker is gone or stuck: cleanup_leftovers removes them on the next start


def foreign_host(request: Request, settings: ServerSettings) -> Response | None:
    if is_allowed_host(request.headers.get("host"), settings.port):
        return None
    return PlainTextResponse("Unknown host.", status_code=400)


async def serve_page(request: Request, settings: ServerSettings) -> Response:
    refused = foreign_host(request, settings)
    if refused is not None:
        return refused
    index = settings.page_dir / "index.html"
    if not index.is_file():
        return PlainTextResponse(NO_PAGE_YET, status_code=404)
    return FileResponse(index, headers={"Content-Security-Policy": CONTENT_SECURITY_POLICY})


async def serve_asset(request: Request, settings: ServerSettings, file_path: str) -> Response:
    refused = foreign_host(request, settings)
    if refused is not None:
        return refused
    assets = (settings.page_dir / "assets").resolve()
    wanted = (assets / file_path).resolve()
    is_inside_assets = wanted.is_relative_to(assets)
    if not is_inside_assets or not wanted.is_file():
        return PlainTextResponse("Not found.", status_code=404)
    return FileResponse(wanted)


def create_app(settings: ServerSettings, sessions: ChatSessions) -> FastAPI:
    actions.settings_widgets = switches_for  # an account change re-sends Settings to every chat

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await run_startup_cleanup()
        yield
        await stop_kernels()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/")
    async def page(request: Request) -> Response:
        return await serve_page(request, settings)

    @app.get("/assets/{file_path:path}")
    async def asset(request: Request, file_path: str) -> Response:
        return await serve_asset(request, settings, file_path)

    @app.websocket("/ws/chat")
    async def chat(websocket: WebSocket, chat_id: str | None = None) -> None:
        await serve_chat(websocket, sessions, chat_id, settings.port)

    return app
