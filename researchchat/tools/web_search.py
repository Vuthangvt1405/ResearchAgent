"""web_search tool: search the internet with DuckDuckGo (via ddgs)."""

import asyncio
import json

from ddgs import DDGS

from researchchat.config import SEARCH_MAX_RESULTS
from researchchat.tools.titles import shorten

DEFINITION = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the internet. Use it for recent events, facts you are "
            "unsure of, or anything that needs a source. Returns titles, "
            "URLs and short snippets. Snippets can be outdated or partial: "
            "use read_page on the best results to get the details."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."}
            },
            "required": ["query"],
        },
    },
}


def search(query: str) -> list[dict]:
    """Search the web. "auto" lets ddgs fall back across engines."""
    try:
        results = DDGS(timeout=10).text(
            query, max_results=SEARCH_MAX_RESULTS, backend="auto"
        )
    except Exception:
        # Free search engines fail now and then; one retry fixes most of it
        results = DDGS(timeout=10).text(
            query, max_results=SEARCH_MAX_RESULTS, backend="auto"
        )
    return [
        {"title": r.get("title"), "url": r.get("href"), "snippet": r.get("body")}
        for r in results
    ]


def step_title(args: dict) -> str:
    return f"Web search: {shorten(str(args.get('query', '')))}"


async def run(args: dict) -> tuple[str, str]:
    """Return (text shown in the chat step, result sent to the model)."""
    query = str(args.get("query", ""))
    if not query:
        raise ValueError("No search query given.")
    results = await asyncio.to_thread(search, query)
    shown = "\n".join(f"- [{r['title']}]({r['url']})" for r in results)
    return shown or "No results.", json.dumps(results, ensure_ascii=False)
