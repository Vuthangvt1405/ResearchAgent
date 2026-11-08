from researchchat.tools import read_page, web_search
from researchchat.tools.titles import TITLE_MAX, short_url, shorten


def test_short_text_is_unchanged():
    assert shorten("Tokyo population") == "Tokyo population"


def test_long_text_is_cut_with_ellipsis():
    out = shorten("x" * 200)
    assert len(out) == TITLE_MAX
    assert out.endswith("…")


def test_long_medium_url_becomes_site_and_page_name():
    url = (
        "https://medium.com/@maria-andraw/"
        "top-10-machine-learning-algorithms-in-2026-65a084ec4208"
    )
    out = short_url(url)
    assert out.startswith("medium.com › top-10-machine-learning")
    assert len(out) <= TITLE_MAX


def test_www_and_trailing_slash_are_dropped():
    assert short_url("https://www.pypi.org/project/chainlit/") == "pypi.org › chainlit"


def test_site_only_url():
    assert short_url("https://example.com/") == "example.com"


def test_encoded_characters_are_readable():
    assert short_url("https://en.wikipedia.org/wiki/S%C3%A3o_Paulo") == (
        "en.wikipedia.org › São_Paulo"
    )


def test_step_titles_use_short_forms():
    long_url = "https://example.com/" + "a" * 300
    assert len(read_page.step_title({"url": long_url})) < 80
    assert len(web_search.step_title({"query": "q " * 200})) < 80
