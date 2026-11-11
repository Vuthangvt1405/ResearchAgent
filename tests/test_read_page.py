import pytest

from researchchat.tools import TOOLS
from researchchat.tools.read_page import check_public_url


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8001",
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://192.168.1.1/",
        "http://10.0.0.5/admin",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
    ],
)
def test_local_and_private_addresses_are_blocked(url):
    with pytest.raises(ValueError, match="public"):
        check_public_url(url)


@pytest.mark.parametrize(
    "url", ["file:///C:/Windows/win.ini", "ftp://example.com/", "not a url"]
)
def test_non_http_urls_are_blocked(url):
    with pytest.raises(ValueError, match="http"):
        check_public_url(url)


def test_public_ip_is_allowed():
    check_public_url("http://1.1.1.1/")


def test_search_tools_are_registered():
    assert [t["function"]["name"] for t in TOOLS] == ["web_search", "read_page", "dataset_search"]
