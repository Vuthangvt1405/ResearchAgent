"""Start the app: `python -m researchchat`, then open http://127.0.0.1:8000."""

import argparse

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def read_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m researchchat", description="Start the research chat on this PC.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="only this PC's own addresses are allowed")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    arguments = read_arguments(argv)
    # Imported here: config and the database must be checked before anything else loads them
    from researchchat.config import ROOT, WORKSPACES_DIR, check_local_host, check_setup

    check_setup()  # wrong Python or no API key: say how to fix it before anything else fails
    # Notebook cells run code, so never serve beyond this PC
    check_local_host(arguments.host)
    from researchchat.db.engine import database_for

    database_for(WORKSPACES_DIR)  # create or upgrade the database now; a damaged or newer file stops here with steps

    import uvicorn

    from researchchat.server.app import ServerSettings, create_app
    from researchchat.server.events import MAX_FRAME_BYTES
    from researchchat.server.socket import ChatSessions

    settings = ServerSettings(port=arguments.port, page_dir=ROOT / "frontend" / "dist")
    app = create_app(settings, ChatSessions())
    uvicorn.run(app, host=arguments.host, port=arguments.port, ws="wsproto", ws_max_size=MAX_FRAME_BYTES)


if __name__ == "__main__":
    main()
