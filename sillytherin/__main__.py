"""How the app starts; run it with `python -m sillytherin`."""

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sillytherin.server.app import ServerSettings

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def read_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m sillytherin", description="Start SillyTherin on this PC.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="only this PC's own addresses are allowed")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--dev", action="store_true", help="also accept the live-reload page from `npm run dev` (port 5173)")
    return parser.parse_args(argv)


DEV_MODE_WARNING = (
    "Dev mode: the app also accepts the live-reload page from `npm run dev` on port 5173. "
    "Start without --dev for normal use."
)


def warn_about_dev_mode() -> None:
    print(DEV_MODE_WARNING, file=sys.stderr)


def server_settings(arguments: argparse.Namespace, page_dir: Path) -> "ServerSettings":
    """What the server needs from the start arguments; only --dev adds the Vite page's origins."""
    from sillytherin.server.app import ServerSettings
    from sillytherin.server.guard import DEV_PAGE_ORIGINS

    extra_origins = DEV_PAGE_ORIGINS if arguments.dev else frozenset()
    return ServerSettings(port=arguments.port, page_dir=page_dir, extra_origins=extra_origins)


def main(argv: list[str] | None = None) -> None:
    arguments = read_arguments(argv)
    # Imported here: config and the database must be checked before anything else loads them
    from sillytherin.config import ROOT, WORKSPACES_DIR, check_local_host, check_setup

    check_setup()  # wrong Python or no API key: say how to fix it before anything else fails
    # Notebook cells run code, so never serve beyond this PC
    check_local_host(arguments.host)
    if arguments.dev:
        warn_about_dev_mode()
    from sillytherin.db.engine import database_for

    database_for(WORKSPACES_DIR)  # create or upgrade the database now; a damaged or newer file stops here with steps

    import uvicorn

    from sillytherin.server.app import create_app
    from sillytherin.server.events import MAX_FRAME_BYTES
    from sillytherin.server.socket import ChatSessions

    app = create_app(server_settings(arguments, ROOT / "frontend" / "dist"), ChatSessions())
    uvicorn.run(app, host=arguments.host, port=arguments.port, ws="wsproto", ws_max_size=MAX_FRAME_BYTES)


if __name__ == "__main__":
    main()
