"""Only the app's own page on this PC may use the app: other websites and rebound host names are refused."""

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.server.conftest import OWN_HOST, OWN_PAGE

# ---- Origin and Host · API
# Baseline: Given the server on port 8000 · When a page opens / and the socket from http://127.0.0.1:8000


def connect(client: TestClient, headers: dict[str, str]) -> dict:
    with client.websocket_connect("/ws/chat", headers=headers) as tab:
        return tab.receive_json()


def refused_code(client: TestClient, headers: dict[str, str]) -> int:
    with pytest.raises(WebSocketDisconnect) as refused:
        connect(client, headers)
    return refused.value.code


def test_local_origin_is_accepted(client):
    # Changed: nothing
    # Then: session.ready
    # Demonstrates: the app's own page connects
    assert connect(client, {"origin": OWN_PAGE, "host": OWN_HOST})["type"] == "session.ready"


def test_localhost_name_origin_is_accepted(client):
    # Changed: Origin http://localhost:8000
    # Then: session.ready
    # Demonstrates: both local names work
    assert connect(client, {"origin": "http://localhost:8000", "host": "localhost:8000"})["type"] == "session.ready"


def test_foreign_origin_is_refused(client, sessions):
    # Changed: Origin https://evil.example
    # Then: close 1008; no chat created
    # Demonstrates: another website can't drive the app
    assert refused_code(client, {"origin": "https://evil.example", "host": OWN_HOST}) == 1008
    assert sessions._chats == {}


def test_missing_origin_is_refused(client, sessions):
    # Changed: no Origin header
    # Then: close 1008; no chat created
    # Demonstrates: a request without an origin can't drive the app
    assert refused_code(client, {"host": OWN_HOST}) == 1008
    assert sessions._chats == {}


def test_null_origin_is_refused(client, sessions):
    # Changed: Origin null
    # Then: close 1008; no chat created
    # Demonstrates: sandboxed pages can't drive the app
    assert refused_code(client, {"origin": "null", "host": OWN_HOST}) == 1008
    assert sessions._chats == {}


def test_rebinding_host_is_refused(client, sessions):
    # Changed: Host evil.example:8000
    # Then: GET / answers 400; the socket closes with 1008
    # Demonstrates: DNS rebinding is blocked
    assert client.get("/", headers={"host": "evil.example:8000"}).status_code == 400
    assert client.get("/assets/app.js", headers={"host": "evil.example:8000"}).status_code == 400
    assert refused_code(client, {"origin": "http://evil.example:8000", "host": "evil.example:8000"}) == 1008
    assert refused_code(client, {"origin": OWN_PAGE, "host": "evil.example:8000"}) == 1008
    assert sessions._chats == {}
