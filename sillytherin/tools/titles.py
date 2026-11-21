"""Short, readable titles for tool steps in the chat."""

from urllib.parse import unquote, urlparse

TITLE_MAX = 50  # longest title text before it's cut with "…"


def shorten(text: str, limit: int = TITLE_MAX) -> str:
    """Cut text to `limit` characters, ending in "…" if it was longer."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def short_url(url: str, limit: int = TITLE_MAX) -> str:
    """Site name plus the last part of the path, e.g.
    "medium.com › top-10-machine-learning-algorithms-in-2026-…"."""
    parts = urlparse(url)
    if not parts.hostname:
        return shorten(url, limit)
    site = parts.hostname.removeprefix("www.")
    last = unquote(parts.path.rstrip("/").rsplit("/", 1)[-1])
    if not last:
        return shorten(site, limit)
    return shorten(f"{site} › {last}", limit)
