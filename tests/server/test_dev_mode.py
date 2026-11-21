"""Dev mode accepts the live-reload page, and only that."""

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import sillytherin.__main__ as command
from sillytherin.__main__ import read_arguments, server_settings
from sillytherin.server.app import ServerSettings, create_app
from sillytherin.server.guard import DEV_PAGE_ORIGINS
from tests.server.conftest import OWN_HOST, OWN_PAGE, PORT

VITE_PAGE = "http://localhost:5173"

# ---- Dev mode · API
# Baseline: Given the app started with --dev · When the Vite dev page http://localhost:5173 opens the socket


@pytest.fixture
def dev_client(services, model, sessions, tmp_path):
    app = create_app(ServerSettings(port=PORT, page_dir=tmp_path / "page", extra_origins=DEV_PAGE_ORIGINS), sessions)
    with TestClient(app, base_url=OWN_PAGE) as test_client:
        yield test_client


def first_event(client: TestClient, origin: str) -> dict:
    # the Vite proxy forwards the socket with the app's own Host and the dev page's Origin
    with client.websocket_connect("/ws/chat", headers={"origin": origin, "host": OWN_HOST}) as tab:
        return tab.receive_json()


def refused_code(client: TestClient, origin: str) -> int:
    with pytest.raises(WebSocketDisconnect) as refused:
        first_event(client, origin)
    return refused.value.code


def test_dev_mode_accepts_the_vite_page(dev_client):
    # Changed: nothing
    # Then: session.ready
    # Demonstrates: live reload works
    assert first_event(dev_client, VITE_PAGE)["type"] == "session.ready"
    assert first_event(dev_client, "http://127.0.0.1:5173")["type"] == "session.ready"


def test_dev_mode_is_off_by_default(tmp_path):
    # Changed: python -m sillytherin arguments without --dev, then with it
    # Then: off, then on
    # Demonstrates: nobody turns it on by accident; the new command reads the flag
    assert command.main.__module__ == "sillytherin.__main__"
    assert server_settings(read_arguments([]), page_dir=tmp_path).extra_origins == frozenset()
    assert server_settings(read_arguments(["--dev"]), page_dir=tmp_path).extra_origins == DEV_PAGE_ORIGINS


def test_vite_page_is_refused_without_dev_mode(client, sessions):
    # Changed: started without --dev
    # Then: close 1008; no chat created
    # Demonstrates: the normal app accepts only its own page
    assert refused_code(client, VITE_PAGE) == 1008
    assert sessions._chats == {}


def test_dev_mode_still_refuses_other_sites(dev_client, sessions):
    # Changed: --dev, Origin https://evil.example or http://localhost:5174
    # Then: close 1008; no chat created
    # Demonstrates: dev mode opens exactly one door
    assert refused_code(dev_client, "https://evil.example") == 1008
    assert refused_code(dev_client, "http://localhost:5174") == 1008
    assert sessions._chats == {}
