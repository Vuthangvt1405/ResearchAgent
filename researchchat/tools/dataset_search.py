"""dataset_search tool: find datasets in public dataset catalogs.

Asks Hugging Face, Zenodo and DataCite at the same time, then merges the
answers into one ranked list with licence, size and popularity, so the model
doesn't have to open each page to compare datasets.
"""

import asyncio
import html
import json
import re
import time

import httpx

from researchchat.config import DATASET_MAX_RESULTS
from researchchat.tools.titles import shorten

DEFINITION = {
    "type": "function",
    "function": {
        "name": "dataset_search",
        "description": (
            "Search dataset catalogs (Hugging Face, Zenodo, DataCite) for "
            "datasets. Prefer this over web_search when the user wants data. "
            "Returns name, URL, description, licence, size, format, downloads "
            "and last update. Use 2-4 plain keywords, not a sentence: "
            "catalogs match on dataset names. If results are poor, try "
            "again with synonyms or fewer words. Hugging Face and Zenodo results "
            "have a `ref` you can pass to dataset_download (only when the user "
            "wants the data in their project)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keywords, e.g. 'credit card fraud'.",
                },
                "task": {
                    "type": "string",
                    "description": (
                        "Optional task filter, e.g. 'text-classification', "
                        "'image-classification', 'tabular-regression'. "
                        "Filters search Hugging Face only."
                    ),
                },
                "language": {
                    "type": "string",
                    "description": (
                        "Optional language code filter, e.g. 'en', 'vi'. "
                        "Filters search Hugging Face only."
                    ),
                },
            },
            "required": ["query"],
        },
    },
}

PER_SOURCE = 8  # results asked from each catalog before merging
DESCRIPTION_MAX = 220
CACHE_SECONDS = 600
_HEADERS = {"User-Agent": "ResearchChat"}
_cache: dict[tuple, tuple[float, list[dict], list[str]]] = {}


def words(text: str) -> list[str]:
    """Lowercase keywords of a query; also strips catalog query syntax."""
    return re.findall(r"\w+", text.lower())


def clean(text: str | None) -> str:
    """Plain one-line text from a catalog description (may hold HTML)."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = text.split("See the full description on the dataset page")[0]
    return shorten(text, DESCRIPTION_MAX)


def _tag(tags: list[str], prefix: str) -> str | None:
    """First 'prefix:value' tag value, e.g. the licence of a Hugging Face dataset."""
    return next((t.split(":", 1)[1] for t in tags if t.startswith(prefix + ":")), None)


def huggingface_item(d: dict) -> dict:
    tags = d.get("tags") or []
    return {
        "source": "Hugging Face",
        "ref": f"hf:{d['id']}",  # what dataset_download takes (NB-3)
        "name": d["id"],
        "url": f"https://huggingface.co/datasets/{d['id']}",
        "description": clean(d.get("description")),
        "license": _tag(tags, "license"),
        "size": _tag(tags, "size_categories"),
        "format": _tag(tags, "format"),
        "downloads": d.get("downloads"),
        "updated": (d.get("lastModified") or "")[:10] or None,
    }


def zenodo_item(d: dict) -> dict:
    meta = d.get("metadata") or {}
    files = d.get("files") or []
    formats = sorted({f["key"].rsplit(".", 1)[-1].lower() for f in files if "." in f.get("key", "")})
    size_mb = sum(f.get("size", 0) for f in files) / 1e6
    return {
        "source": "Zenodo",
        "ref": f"zenodo:{d['id']}" if d.get("id") else None,  # DataCite items get no ref (A18)
        "name": meta.get("title") or d.get("title"),
        "url": (d.get("links") or {}).get("self_html") or d.get("doi_url"),
        "description": clean(meta.get("description")),
        "license": (meta.get("license") or {}).get("id"),
        "size": f"{size_mb:,.1f} MB" if files else None,
        "format": ", ".join(formats[:4]) or None,
        "downloads": (d.get("stats") or {}).get("downloads"),
        "updated": (d.get("modified") or "")[:10] or None,
    }


def datacite_item(d: dict) -> dict:
    a = d.get("attributes") or {}
    descriptions = a.get("descriptions") or [{}]
    rights = [r.get("rightsIdentifier") for r in a.get("rightsList") or [] if r.get("rightsIdentifier")]
    return {
        "source": a.get("publisher") or "DataCite",
        "name": ((a.get("titles") or [{}])[0]).get("title"),
        "url": a.get("url") or f"https://doi.org/{a.get('doi')}",
        "description": clean(descriptions[0].get("description")),
        "license": rights[0] if rights else None,
        "size": ", ".join(a.get("sizes") or []) or None,
        "format": ", ".join(a.get("formats") or []) or None,
        "downloads": a.get("downloadCount") or None,
        "updated": (a.get("updated") or "")[:10] or None,
    }


async def _huggingface(client: httpx.AsyncClient, query: str, task: str, language: str) -> list[dict]:
    params: list[tuple[str, str]] = [
        ("search", " ".join(words(query))),
        ("sort", "downloads"),
        ("direction", "-1"),
        ("limit", str(PER_SOURCE)),
    ]
    if task:
        params.append(("filter", f"task_categories:{task}"))
    if language:
        params.append(("filter", f"language:{language}"))
    r = await client.get("https://huggingface.co/api/datasets", params=params)
    r.raise_for_status()
    return [huggingface_item(d) for d in r.json()]


async def _zenodo(client: httpx.AsyncClient, query: str, task: str, language: str) -> list[dict]:
    r = await client.get(
        "https://zenodo.org/api/records",
        params={"q": " ".join(words(query)), "type": "dataset", "size": PER_SOURCE, "sort": "bestmatch"},
    )
    r.raise_for_status()
    return [zenodo_item(d) for d in r.json()["hits"]["hits"]]


async def _datacite(client: httpx.AsyncClient, query: str, task: str, language: str) -> list[dict]:
    # Title match keeps it on topic; a plain query matches any field and drifts
    r = await client.get(
        "https://api.datacite.org/dois",
        params={
            "query": f"titles.title:({' AND '.join(words(query))})",
            "resource-type-id": "dataset",
            "page[size]": PER_SOURCE,
            "sort": "relevance",
        },
    )
    r.raise_for_status()
    items = [datacite_item(d) for d in r.json()["data"]]
    # Zenodo records are also in DataCite; the Zenodo source has more detail
    return [i for i in items if "zenodo.org" not in (i["url"] or "")]


SOURCES = {"Hugging Face": _huggingface, "Zenodo": _zenodo, "DataCite": _datacite}
FILTERABLE = {"Hugging Face"}  # the only catalog that knows tasks and languages


def score(item: dict, keywords: list[str]) -> float:
    """How well a dataset matches the keywords: a name hit counts double."""
    if not keywords:
        return 0.0
    name = (item.get("name") or "").lower()
    body = (item.get("description") or "").lower()
    hits = sum(2 if k in name else 1 if k in body else 0 for k in keywords)
    return hits / (2 * len(keywords))


def merge(per_source: list[list[dict]], query: str, limit: int) -> list[dict]:
    """One list from all catalogs: best keyword match first, then each
    catalog's own order, so the top of every catalog gets a place."""
    keywords = words(query)
    ranked, seen = [], set()
    for items in per_source:
        for rank, item in enumerate(items):
            key = (item.get("name") or "").lower()
            if not item.get("url") or not key or key in seen:
                continue  # e.g. several versions of one record
            seen.add(key)
            ranked.append((-score(item, keywords), rank, item))
    ranked.sort(key=lambda t: t[:2])
    return [{k: v for k, v in item.items() if v not in (None, "")} for _, _, item in ranked[:limit]]


async def search(query: str, task: str = "", language: str = "") -> tuple[list[dict], list[str]]:
    """Return (datasets, names of catalogs that failed)."""
    key = (" ".join(words(query)), task, language)
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1], cached[2]

    # With a filter, catalogs that can't apply it would add off-target results
    sources = {n: s for n, s in SOURCES.items() if n in FILTERABLE} if task or language else SOURCES
    async with httpx.AsyncClient(timeout=10, headers=_HEADERS, follow_redirects=True) as client:
        answers = await asyncio.gather(
            *(source(client, query, task, language) for source in sources.values()),
            return_exceptions=True,
        )
    failed = [name for name, a in zip(sources, answers) if isinstance(a, BaseException)]
    if len(failed) == len(sources):
        raise ValueError("None of the dataset catalogs answered. Try again, or use web_search.")
    results = merge([a for a in answers if isinstance(a, list)], query, DATASET_MAX_RESULTS)
    if not failed:  # don't remember a partial answer
        _cache[key] = (time.monotonic(), results, failed)
    return results, failed


def step_title(args: dict) -> str:
    return f"Dataset search: {shorten(str(args.get('query', '')))}"


def _line(r: dict) -> str:
    extra = [r["source"], r.get("license"), r.get("size")]
    if r.get("downloads"):
        extra.append(f"{r['downloads']:,} downloads")
    return f"- [{r['name']}]({r['url']}) · " + " · ".join(e for e in extra if e)


async def run(args: dict) -> tuple[str, str]:
    """Return (text shown in the chat step, result sent to the model)."""
    query = str(args.get("query", ""))
    if not words(query):
        raise ValueError("No search query given.")
    results, failed = await search(query, str(args.get("task") or ""), str(args.get("language") or ""))
    shown = "\n".join(_line(r) for r in results) or "No datasets found."
    payload: dict = {"datasets": results}
    if failed:
        note = f"No answer from: {', '.join(failed)}."
        shown += f"\n\n{note}"
        payload["note"] = note
    if not results:
        payload["hint"] = "Try fewer or different keywords, or web_search."
    return shown, json.dumps(payload, ensure_ascii=False)
