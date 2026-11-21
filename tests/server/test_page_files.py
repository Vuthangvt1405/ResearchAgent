"""The built page and its files are served from page_dir only."""

import pytest
from starlette.testclient import TestClient

from sillytherin.server.app import (
    CONTENT_SECURITY_POLICY,
    NO_PAGE_YET,
    ServerSettings,
    create_app,
)
from tests.server.conftest import OWN_PAGE, PORT

# ---- Page files · API
# Baseline: Given a built page in page_dir · When the browser asks for it


@pytest.fixture
def page_dir(tmp_path):
    page = tmp_path / "dist"
    (page / "assets").mkdir(parents=True)
    (page / "index.html").write_text("<!doctype html><title>SillyTherin</title>")
    (page / "assets" / "app.js").write_text("console.log('page');")
    (tmp_path / "config.toml").write_text("secret = true")  # beside the page, never to be served
    return page


@pytest.fixture
def page_client(services, model, sessions, page_dir):
    app = create_app(ServerSettings(port=PORT, page_dir=page_dir), sessions)
    with TestClient(app, base_url=OWN_PAGE) as test_client:
        yield test_client


def test_page_is_served_with_its_security_policy(page_client):
    # Changed: nothing
    # Then: GET / answers 200 with index.html and the Content-Security-Policy header
    # Demonstrates: the page loads with its rules
    page = page_client.get("/")
    assert page.status_code == 200 and "<title>SillyTherin</title>" in page.text
    assert page.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert "googleapis" not in CONTENT_SECURITY_POLICY and "script-src 'self'" in CONTENT_SECURITY_POLICY


def test_page_files_are_served(page_client):
    # Changed: GET /assets/app.js
    # Then: 200 with the file
    # Demonstrates: the page's scripts and styles load
    script = page_client.get("/assets/app.js")
    assert script.status_code == 200 and "console.log" in script.text


def test_files_outside_the_page_are_refused(page_client):
    # Changed: GET /assets/../../config.toml, and the encoded form
    # Then: 404; nothing outside assets/ is read
    # Demonstrates: no file leaks
    for path in ("/assets/../../config.toml", "/assets/..%2F..%2Fconfig.toml", "/assets/%2e%2e/%2e%2e/config.toml", "/assets/../index.html"):
        answer = page_client.get(path)
        assert "secret" not in answer.text, path
        assert answer.status_code == 404 or "<title>SillyTherin</title>" in answer.text, path


def test_missing_page_says_it_isnt_built(client):
    # Changed: no index.html
    # Then: 404 The SillyTherin page isn't built yet.
    # Demonstrates: a clear message instead of a crash
    answer = client.get("/")
    assert (answer.status_code, answer.text) == (404, NO_PAGE_YET)
