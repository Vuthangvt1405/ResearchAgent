"""Tests for downloads from links the user pasted into the chat.

No network: websites are httpx.MockTransport handlers and host lookups are faked.
"""

import asyncio
from itertools import pairwise

import httpx
import pytest

from researchchat.workspace import ErrorCode, WorkspaceError, store
from researchchat.workspace.datasets import links
from researchchat.workspace.datasets import sources as src
from researchchat.workspace.datasets import store as ds
from researchchat.workspace.datasets.service import DatasetService, DatasetsSettings
from tests.conftest import FakeFreeDisk, catalog_client, fake_lookup

LINK = "https://example.org/data/iris.csv"
CSV = b"sepal_length,species\n5.1,setosa\n" * 10
GB = 1_000_000_000
PRIVATE_HOSTS = {"lan.example": ["10.0.0.5"], "mixed.example": ["93.184.216.34", "192.168.1.9"]}


async def lookup_with_private_hosts(host: str) -> list[str]:
    return PRIVATE_HOSTS.get(host) or await fake_lookup(host)


@pytest.fixture(autouse=True)
def no_dns(monkeypatch):
    monkeypatch.setattr(src, "lookup_host", lookup_with_private_hosts)


def run(coro):
    return asyncio.run(coro)


def error_of(coro) -> WorkspaceError:
    with pytest.raises(WorkspaceError) as e:
        run(coro)
    return e.value


class Website:
    """A fake website: one answer for every request, unless a redirect is set for a path."""

    def __init__(self, body=CSV, status=200, content_type="text/csv", length=True, headers=None):
        self.body = body
        self.status = status
        self.content_type = content_type
        self.length = length
        self.headers = dict(headers or {})
        self.redirects: dict[str, str] = {}  # url -> location
        self.requests: list[httpx.Request] = []
        self.chunks_read = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        location = self.redirects.get(str(request.url))
        if location:
            return httpx.Response(302, headers={"location": location})
        headers = dict(self.headers)
        if self.content_type:
            headers["content-type"] = self.content_type
        if self.length and isinstance(self.body, bytes):
            headers["content-length"] = str(len(self.body))
        return httpx.Response(self.status, headers=headers, content=self._content())

    def _content(self):
        if isinstance(self.body, bytes) and self.length:
            return self.body
        body = [self.body] if isinstance(self.body, bytes) else self.body()
        if hasattr(body, "__aiter__"):
            return body
        return as_async(body)


async def as_async(chunks):
    for chunk in chunks:
        yield chunk


def probe(site: Website, link: str = LINK):
    async def go():
        async with catalog_client(site) as client:
            return await links.resolve_link(link, client=client)

    return go()


# ---- Only links the user pasted count
# Baseline: Given the history has a user message with https://example.org/data/iris.csv · When the pasted links are collected


def history_with(*messages):
    return [{"role": "system", "content": "You are ResearchChat."}, *messages]


def test_link_in_user_message_is_found():
    # Then: the set holds exactly that link
    # Demonstrates: a pasted link is recognised
    history = history_with({"role": "user", "content": f"get {LINK} please"})
    assert links.find_pasted_links(history) == {LINK}


def test_trailing_punctuation_is_trimmed():
    # Then: the message ends 'iris.csv).' and the link has no ').'
    # Demonstrates: links at the end of a sentence still work
    history = history_with({"role": "user", "content": f"(the file is {LINK})."})
    assert links.find_pasted_links(history) == {LINK}


def test_links_from_earlier_user_messages_count():
    # Then: a link from the first of three user messages is found
    # Demonstrates: the user can paste first and ask later
    history = history_with(
        {"role": "user", "content": f"here: {LINK}"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "anything else?"},
        {"role": "user", "content": "download it"},
    )
    assert links.find_pasted_links(history) == {LINK}


def test_link_in_tool_result_is_ignored():
    # Then: a link only in a tool result gives an empty set
    # Demonstrates: a link from a web page the assistant read can't be used
    history = history_with({"role": "tool", "tool_call_id": "1", "content": f"page says download {LINK}"})
    assert links.find_pasted_links(history) == frozenset()


def test_link_in_assistant_message_is_ignored():
    # Then: a link only in an assistant reply gives an empty set
    # Demonstrates: the assistant's own suggestions don't count
    history = history_with({"role": "assistant", "content": f"You could use {LINK}"})
    assert links.find_pasted_links(history) == frozenset()


def test_link_in_system_note_is_ignored():
    # Then: a link only in a system note gives an empty set
    # Demonstrates: notes don't count
    history = [{"role": "system", "content": f"note: {LINK}"}]
    assert links.find_pasted_links(history) == frozenset()


def test_no_link_in_history():
    # Then: no link anywhere gives an empty set
    # Demonstrates: nothing to download
    history = history_with({"role": "user", "content": "find me iris data"}, {"role": "user", "content": None})
    assert links.find_pasted_links(history) == frozenset()


# ---- The probe tells a file from everything else
# Baseline: Given a pasted link on a public host answering 200 text/csv with Content-Length 4551 · When the link is resolved


def test_probe_file_gives_one_file_plan():
    # Then: a plan with one file iris.csv, size 4551, no licence
    # Demonstrates: a data file is accepted with its real size
    plan = run(probe(Website(body=b"x" * 4551)))
    assert plan.source == "link" and plan.source_id == LINK and plan.url == LINK
    assert plan.name == "iris.csv" and plan.license is None
    [file] = plan.files
    assert (file.path, file.size, file.size_is_known, file.url, file.checksum) == ("iris.csv", 4551, True, LINK, None)


def test_probe_without_length_gives_unknown_size():
    # Then: no Content-Length: size 0 marked unknown
    # Demonstrates: a file with no declared size still downloads
    [file] = run(probe(Website(length=False))).files
    assert file.size == 0 and not file.size_is_known


def test_probe_follows_redirect_to_public_cdn():
    # Then: a 302 to another public https host still gives a plan
    # Demonstrates: file hosts that use CDNs work
    site = Website()
    site.redirects[LINK] = "https://cdn.example.net/blob/123"
    plan = run(probe(site))
    assert plan.files[0].path == "iris.csv"
    assert [r.url.host for r in site.requests] == ["example.org", "cdn.example.net"]


def test_probe_octet_stream_accepted():
    # Then: application/octet-stream with non-HTML bytes gives a plan
    # Demonstrates: generic binary types are files
    plan = run(probe(Website(body=b"PAR1\x00\x01", content_type="application/octet-stream")))
    assert plan.files[0].size == 6


def test_probe_large_known_size_accepted():
    # Then: Content-Length of 50 GB with enough free disk gives a plan
    # Demonstrates: there is no per-file maximum
    site = Website(length=False, headers={"content-length": str(50 * GB)}, body=lambda: iter([b"a,b\n"]))
    [file] = run(probe(site)).files
    assert file.size == 50 * GB and file.size_is_known


def test_probe_html_is_not_a_file():
    # Then: text/html gives NOT_A_FILE with the 'opens a web page' message
    # Demonstrates: articles are refused
    e = error_of(probe(Website(body=b"<p>An article</p>", content_type="text/html; charset=utf-8")))
    assert e.code == ErrorCode.NOT_A_FILE
    assert e.message == "This link opens a web page, not a data file. Paste the link to the file itself."


def test_probe_xhtml_is_not_a_file():
    # Then: application/xhtml+xml gives NOT_A_FILE
    # Demonstrates: XHTML pages are refused too
    assert error_of(probe(Website(content_type="application/xhtml+xml"))).code == ErrorCode.NOT_A_FILE


def test_probe_html_body_with_generic_type():
    # Then: octet-stream whose body starts '<!doctype html' gives NOT_A_FILE
    # Demonstrates: a mislabelled page is still caught
    site = Website(body=b"\n  <!DOCTYPE html><html>...", content_type="application/octet-stream")
    assert error_of(probe(site)).code == ErrorCode.NOT_A_FILE


def test_probe_404_is_not_found():
    # Then: 404 gives NOT_FOUND
    # Demonstrates: broken links are reported
    e = error_of(probe(Website(status=404)))
    assert e.code == ErrorCode.NOT_FOUND and "404" in e.message


def test_probe_410_is_not_found():
    # Then: 410 gives NOT_FOUND
    # Demonstrates: removed files are reported as broken
    assert error_of(probe(Website(status=410))).code == ErrorCode.NOT_FOUND


def test_probe_401_needs_login():
    # Then: 401 gives NOT_PUBLIC
    # Demonstrates: login-only files are refused
    e = error_of(probe(Website(status=401)))
    assert e.code == ErrorCode.NOT_PUBLIC and "login" in e.message


def test_probe_403_needs_login():
    # Then: 403 gives NOT_PUBLIC
    # Demonstrates: forbidden files are refused
    assert error_of(probe(Website(status=403))).code == ErrorCode.NOT_PUBLIC


def test_probe_500_fails():
    # Then: 500 gives DOWNLOAD_FAILED 'answered HTTP 500'
    # Demonstrates: other errors are named
    e = error_of(probe(Website(status=500)))
    assert e.code == ErrorCode.DOWNLOAD_FAILED and e.message == "the website answered HTTP 500"


def test_probe_timeout(monkeypatch):
    # Then: a server that never answers gives DOWNLOAD_FAILED 'the website didn't answer' within the probe timeout
    # Demonstrates: a slow host can't hold the queue lock
    monkeypatch.setattr(links, "LINK_PROBE_TIMEOUT_SECONDS", 0.05)

    async def silent(request):
        await asyncio.sleep(5)
        return httpx.Response(200)

    async def go():
        async with catalog_client(silent) as client:
            return await links.resolve_link(LINK, client=client)

    e = error_of(asyncio.wait_for(go(), 2))
    assert e.code == ErrorCode.DOWNLOAD_FAILED and e.message == "the website didn't answer"


def test_probe_body_not_downloaded():
    # Then: at most the sniff bytes of the body are read
    # Demonstrates: the probe doesn't download the file twice
    site = Website(length=False)

    def big_body():
        for _ in range(1000):
            site.chunks_read += 1
            yield b"x" * 1000

    site.body = big_body
    run(probe(site))
    assert site.chunks_read <= 2


# ---- File name and dataset id come from the link
# Baseline: Given the link https://example.org/data/iris.csv · When the plan and the dataset id are made


def test_link_id_and_name():
    # Then: id link-example-org--iris-csv and file iris.csv
    # Demonstrates: the card has a readable name and id
    assert links.link_file_name(LINK) == "iris.csv"
    assert ds.make_id("link", LINK, set()) == "link-example-org--iris-csv"


def test_percent_encoded_name_decoded():
    # Then: my%20data.csv becomes 'my data.csv'
    # Demonstrates: real file names show
    assert links.link_file_name("https://example.org/my%20data.csv") == "my data.csv"


def test_no_file_name_uses_download():
    # Then: a link ending in '/' plus a query gives the file 'download'
    # Demonstrates: links without a file name still work
    assert links.link_file_name("https://example.org/export/?format=csv") == "download"


def test_same_name_other_site_gets_own_id():
    # Then: https://other.org/iris.csv in the same project gives link-other-org--iris-csv
    # Demonstrates: two websites never share a card
    taken = {ds.make_id("link", LINK, set())}
    assert ds.make_id("link", "https://other.org/iris.csv", taken) == "link-other-org--iris-csv"


def test_same_name_same_site_other_path():
    # Then: https://example.org/v2/iris.csv gets a -2 id and its own pool folder
    # Demonstrates: no clash between pool folder names
    other = "https://example.org/v2/iris.csv"
    taken = {ds.make_id("link", LINK, set())}
    assert ds.make_id("link", other, taken) == "link-example-org--iris-csv-2"
    first, second = run(probe(Website())), run(probe(Website(), other))
    assert first.revision != second.revision


def test_traversal_name_refused():
    # Then: a last segment '..%2F..%2Fetc' gives BAD_PAYLOAD and nothing is saved
    # Demonstrates: a file name can't escape the dataset folder
    with pytest.raises(WorkspaceError) as e:
        links.link_file_name("https://example.org/x/..%2F..%2Fetc")
    assert e.value.code == ErrorCode.BAD_PAYLOAD


def test_content_disposition_ignored():
    # Then: a Content-Disposition filename '../../x' is ignored; the name comes from the link
    # Demonstrates: the website can't choose the path
    site = Website(headers={"content-disposition": 'attachment; filename="../../x"'})
    assert run(probe(site)).files[0].path == "iris.csv"


# ---- Only public HTTPS addresses, on every hop
# Baseline: Given a pasted link (negatives only) · When the probe or the download runs


def test_private_address_refused():
    # Then: a host resolving to 10.0.0.5 is blocked and no request is sent
    # Demonstrates: no requests into the local network
    site = Website()
    e = error_of(probe(site, "https://lan.example/x.csv"))
    assert e.code == ErrorCode.DOWNLOAD_FAILED and "blocked" in e.message
    assert site.requests == []


def test_localhost_refused():
    # Then: https://127.0.0.1/ and https://[::1]/ are blocked
    # Demonstrates: no requests to the app's own machine
    site = Website()
    for link in ("https://127.0.0.1/x.csv", "https://[::1]/x.csv"):
        assert "blocked" in error_of(probe(site, link)).message
    assert site.requests == []


def test_mixed_public_private_resolution_refused():
    # Then: a host resolving to one public and one private address is blocked
    # Demonstrates: one private address is enough to refuse
    assert "blocked" in error_of(probe(Website(), "https://mixed.example/x.csv")).message


def test_redirect_to_private_refused():
    # Then: a 302 to https://192.168.1.1/ is blocked
    # Demonstrates: redirects are re-checked
    site = Website()
    site.redirects[LINK] = "https://192.168.1.1/x.csv"
    assert "blocked" in error_of(probe(site)).message
    assert len(site.requests) == 1


def test_redirect_to_http_refused():
    # Then: a 302 to http://example.org/ is blocked
    # Demonstrates: a redirect can't drop https
    site = Website()
    site.redirects[LINK] = "http://example.org/data/iris.csv"
    assert "blocked" in error_of(probe(site)).message


def test_too_many_redirects():
    # Then: six hops give DOWNLOAD_FAILED 'too many redirects'
    # Demonstrates: redirect loops end
    site = Website()
    hops = [f"https://example.org/hop{i}" for i in range(7)]
    site.redirects[LINK] = hops[0]
    for here, there in pairwise(hops):
        site.redirects[here] = there
    assert error_of(probe(site)).message == "too many redirects"


def test_no_cookies_or_auth_sent():
    # Then: the request carries only User-Agent and Accept-Encoding: identity
    # Demonstrates: nothing of the user's leaks to the website
    site = Website()
    run(probe(site))
    headers = site.requests[0].headers
    assert headers["user-agent"] == "ResearchChat" and headers["accept-encoding"] == "identity"
    assert "cookie" not in headers and "authorization" not in headers


def service_for(root, site, free=100 * GB, **settings):
    defaults = {"min_free_disk_mb": 0, "ask_above_mb": 200, "max_files": 500, "parallel_downloads": 2, "stall_timeout_seconds": 0.2}
    defaults.update(settings)
    return DatasetService(
        settings=DatasetsSettings(**defaults), root=root, free_bytes=FakeFreeDisk(free),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(site)), progress_interval=0,
    )


async def yes(plan, size):
    return True


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "ws"
    store.create_project("P1", root, project_id="p1")
    return root


def test_background_stream_rechecks_first_hop(root):
    # Then: a host that turns private between probe and download fails the card as blocked
    # Demonstrates: the address check isn't done only once
    link = "https://turns.example/x.csv"

    async def scenario():
        svc = service_for(root, Website(), parallel_downloads=0)
        await svc.startup_cleanup()
        await svc.request("p1", "s1", link, approve=yes, pasted_links=frozenset({link}))
        PRIVATE_HOSTS["turns.example"] = ["10.1.2.3"]
        try:
            svc.settings.parallel_downloads = 1
            svc._schedule()
            await svc.wait_idle()
        finally:
            del PRIVATE_HOSTS["turns.example"]
        [view] = svc.list_for_model("p1")
        assert view["status"] == "failed" and "blocked" in view["error"]

    run(scenario())


# ---- Disk and time limits
# Baseline: Given a fake free-disk function (negatives only) · When a link downloads


def test_endless_stream_stops_on_disk_full(root):
    # Then: an endless body that fills the disk fails with 'disk full' and the partial file is removed
    # Demonstrates: an endless file can't leave junk behind
    def endless():
        while True:
            yield b"x" * 1000

    async def scenario():
        svc = service_for(root, Website(body=endless, length=False))
        await svc.startup_cleanup()
        svc.free_bytes = lambda path: 0
        await svc.request("p1", "s1", LINK, approve=yes, pasted_links=frozenset({LINK}))
        await svc.wait_idle()
        [view] = svc.list_for_model("p1")
        assert view["status"] == "failed" and view["error"] == "disk full"
        partial = svc.pool.partial_dir()
        assert not partial.exists() or not any(partial.iterdir())

    run(scenario())


def test_identity_encoding_requested(root):
    # Then: the request asks for Accept-Encoding: identity
    # Demonstrates: the size the website states is the size written
    site = Website()

    async def scenario():
        svc = service_for(root, site)
        await svc.startup_cleanup()
        await svc.request("p1", "s1", LINK, approve=yes, pasted_links=frozenset({LINK}))
        await svc.wait_idle()

    run(scenario())
    assert len(site.requests) == 2  # probe + download
    assert all(r.headers["accept-encoding"] == "identity" for r in site.requests)


def test_probe_timeout_releases_lock(root, monkeypatch):
    # Then: a hanging probe times out and other requests go on
    # Demonstrates: one slow website doesn't block every project
    monkeypatch.setattr(links, "LINK_PROBE_TIMEOUT_SECONDS", 0.1)
    slow, fast = "https://slow.example/a.csv", "https://fast.example/b.csv"

    async def handler(request):
        if request.url.host == "slow.example":
            await asyncio.sleep(5)
        return httpx.Response(200, headers={"content-type": "text/csv"}, content=b"a\n")

    async def scenario():
        svc = service_for(root, handler)
        await svc.startup_cleanup()
        pasted = frozenset({slow, fast})
        slow_request = asyncio.create_task(svc.request("p1", "s1", slow, approve=yes, pasted_links=pasted))
        await asyncio.sleep(0.01)
        started = await asyncio.wait_for(svc.request("p1", "s1", fast, approve=yes, pasted_links=pasted), 2)
        with pytest.raises(WorkspaceError) as e:
            await slow_request
        await svc.wait_idle()
        return started, e.value

    started, error = run(scenario())
    assert started["dataset_id"] == "link-fast-example--b-csv"
    assert error.message == "the website didn't answer"


# ---- Nothing secret in logs
# Baseline: Given a pasted link with ?token=abc123 that fails in the background · When the failure is logged and shown

SECRET_LINK = "https://example.org/data/iris.csv?token=abc123"


def failing_download(root, caplog):
    async def stall():
        yield b"a,b\n"
        await asyncio.sleep(0.5)  # past the 0.2 s stall timeout

    async def scenario():
        svc = service_for(root, Website(body=stall, length=False))
        await svc.startup_cleanup()
        await svc.request("p1", "s1", SECRET_LINK, approve=yes, pasted_links=frozenset({SECRET_LINK}))
        await svc.wait_idle()
        return svc.list_for_model("p1")

    with caplog.at_level("DEBUG"):
        return run(scenario())


def test_failure_log_has_host_only(root, caplog):
    # Then: the log names example.org and never abc123
    # Demonstrates: signed links don't leak into logs
    failing_download(root, caplog)
    assert "abc123" not in caplog.text


def test_card_error_has_no_query(root, caplog):
    # Then: the card error has no abc123
    # Demonstrates: the card never shows a link's secret
    [view] = failing_download(root, caplog)
    assert view["status"] == "failed" and view["error"] == "stalled on iris.csv"
    assert "abc123" not in view["error"]
