"""read_page tool: open a public web page and return its text."""

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

from ddgs import DDGS

from researchchat.config import READ_PAGE_MAX_CHARS
from researchchat.tools.titles import short_url

DEFINITION = {
    "type": "function",
    "function": {
        "name": "read_page",
        "description": (
            "Open a web page and return its text. Use it on URLs from "
            "web_search results when you need more than the snippet. "
            "Cite the URL in your answer."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full http(s) URL."}
            },
            "required": ["url"],
        },
    },
}


def check_public_url(url: str) -> None:
    """Only allow public http(s) pages, so the model can't reach this machine
    or your local network (e.g. if a web page tells it to)."""
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("Only http(s) URLs can be read.")
    for info in socket.getaddrinfo(parts.hostname, None):
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise ValueError("Only public web pages can be read.")


def read_page(url: str) -> str:
    """Fetch a page and return its text, cut to READ_PAGE_MAX_CHARS."""
    check_public_url(url)
    try:
        content = DDGS(timeout=15).extract(url, fmt="text_plain")["content"]
    except Exception as e:
        # ddgs errors repeat the whole URL; keep the message short
        if "timed out" in str(e).lower():
            raise ValueError("The site took too long to respond.") from e
        raise ValueError(
            "Couldn't open the page (the site may block automated reading)."
        ) from e
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")
    text = content.strip()
    if not text:
        raise ValueError("The page had no readable text.")
    if len(text) > READ_PAGE_MAX_CHARS:
        text = (
            text[:READ_PAGE_MAX_CHARS]
            + f"\n\n[Page cut off at {READ_PAGE_MAX_CHARS:,} characters.]"
        )
    return text


def step_title(args: dict) -> str:
    return f"Read page: {short_url(str(args.get('url', '')))}"


async def run(args: dict) -> tuple[str, str]:
    """Return (text shown in the chat step, result sent to the model)."""
    url = str(args.get("url", ""))
    if not url:
        raise ValueError("No URL given.")
    text = await asyncio.to_thread(read_page, url)
    # The title is shortened, so give the full link here
    shown = f"[{url}]({url})\n\nRead {len(text):,} characters.\n\n{text[:500]}…"
    return shown, text
