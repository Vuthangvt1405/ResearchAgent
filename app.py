import asyncio
import ipaddress
import json
import os
import socket
import tomllib
from pathlib import Path
from urllib.parse import urlparse

import chainlit as cl
import httpx
from chainlit.input_widget import Select, Switch
from ddgs import DDGS
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

with open(Path(__file__).parent / "config.toml", "rb") as f:
    CONFIG = tomllib.load(f)

OPENROUTER_URL = CONFIG["openrouter"]["base_url"]
MODEL = os.getenv("OPENROUTER_MODEL") or CONFIG["openrouter"]["model"]
SYSTEM_PROMPT = CONFIG["chat"]["system_prompt"]
GREETING = CONFIG["chat"]["greeting"]

# Effort levels: OpenRouter level -> label shown in the settings panel.
ALLOWED_LEVELS = {"default", "off", "minimal", "low", "medium", "high", "xhigh"}
EFFORT_LEVELS: dict[str, str] = CONFIG["thinking"]["levels"]
unknown = set(EFFORT_LEVELS) - ALLOWED_LEVELS
if unknown:
    raise ValueError(
        f"config.toml [thinking.levels]: unknown level(s) {sorted(unknown)}. "
        f"Allowed: {sorted(ALLOWED_LEVELS)}"
    )
EFFORT_DEFAULT = CONFIG["thinking"].get("default", "default")
if EFFORT_DEFAULT not in EFFORT_LEVELS:
    EFFORT_DEFAULT = next(iter(EFFORT_LEVELS))

SEARCH_CONFIG = CONFIG.get("web_search", {})
SEARCH_ENABLED = SEARCH_CONFIG.get("enabled", True)
SEARCH_MAX_RESULTS = SEARCH_CONFIG.get("max_results", 5)
SEARCH_MAX_ROUNDS = SEARCH_CONFIG.get("max_rounds", 3)
READ_PAGE_MAX_CHARS = SEARCH_CONFIG.get("read_page_max_chars", 8000)

TOOLS = [
    {
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
    },
    {
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
    },
]

LIMIT_NOTE = {
    "role": "system",
    "content": (
        "Tool limit reached. Do not search or read more pages. Answer the "
        "user now using the results above, and cite the URLs you used."
    ),
}

client = AsyncOpenAI(
    base_url=OPENROUTER_URL,
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

_model_params: set[str] | None = None


async def model_params() -> set[str]:
    """Ask OpenRouter once which request parameters MODEL supports."""
    global _model_params
    if _model_params is None:
        try:
            async with httpx.AsyncClient(timeout=10) as http:
                resp = await http.get(f"{OPENROUTER_URL}/models")
                resp.raise_for_status()
            model = next(
                (m for m in resp.json()["data"] if m["id"] == MODEL), {}
            )
            _model_params = set(model.get("supported_parameters", []))
        except Exception:
            return set()  # don't cache, so the next chat retries
    return _model_params


def reasoning_body(settings: dict) -> dict:
    """Build the OpenRouter `reasoning` request field from chat settings."""
    if "thinking_effort" not in settings:  # model has no reasoning support
        return {}
    effort = settings["thinking_effort"]
    if effort == "off":
        return {"reasoning": {"enabled": False}}
    reasoning: dict = {}
    if effort != "default":
        reasoning["effort"] = effort
    if not settings.get("show_thinking", True):
        reasoning["exclude"] = True
    return {"reasoning": reasoning} if reasoning else {}


def web_search(query: str) -> list[dict]:
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
    content = DDGS(timeout=15).extract(url, fmt="text_plain")["content"]
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


async def run_tool_call(call: dict) -> str:
    """Run one tool call inside a visible step and return its result as text."""
    try:
        args = json.loads(call["arguments"] or "{}")
    except json.JSONDecodeError:
        args = {}
    tool = call["name"]
    query = str(args.get("query", ""))
    url = str(args.get("url", ""))
    if tool == "web_search":
        title = f"Web search: {query}"
    elif tool == "read_page":
        title = f"Read page: {url}"
    else:
        title = f"Unknown tool: {tool}"

    async with cl.Step(name=title, type="tool", show_input=False) as step:
        try:
            if tool == "web_search" and query:
                results = await asyncio.to_thread(web_search, query)
                step.output = "\n".join(
                    f"- [{r['title']}]({r['url']})" for r in results
                ) or "No results."
                return json.dumps(results, ensure_ascii=False)
            if tool == "read_page" and url:
                text = await asyncio.to_thread(read_page, url)
                step.output = f"Read {len(text):,} characters.\n\n{text[:500]}…"
                return text
            raise ValueError(f"Bad tool call: {tool}({call['arguments']})")
        except Exception as e:
            step.output = f"Failed: {e}"
            return f"Tool failed: {e}"


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set(
        "history", [{"role": "system", "content": SYSTEM_PROMPT}]
    )
    params = await model_params()
    widgets = []
    if "reasoning" in params:
        widgets += [
            Select(
                id="thinking_effort",
                label="Thinking effort",
                # Chainlit items are {label: value}; the panel returns the value.
                items={label: level for level, label in EFFORT_LEVELS.items()},
                initial_value=EFFORT_DEFAULT,
                description="How much the model reasons before answering.",
            ),
            Switch(
                id="show_thinking",
                label="Show thinking",
                initial=True,
                description="Show the model's reasoning above its answer.",
            ),
        ]
    if "tools" in params:
        widgets.append(
            Switch(
                id="web_search",
                label="Web search",
                initial=SEARCH_ENABLED,
                description="Let the model search the internet and read pages when it needs to.",
            )
        )
    settings = await cl.ChatSettings(widgets).send() if widgets else {}
    cl.user_session.set("settings", settings)
    await cl.Message(content=GREETING).send()


@cl.on_settings_update
async def on_settings_update(settings: dict):
    cl.user_session.set("settings", settings)


async def stream_round(
    messages: list, reply: cl.Message, extra: dict
) -> tuple[str, list[dict]]:
    """Stream one model response into the UI.

    Returns the text written this round and any tool calls the model made.
    """
    text = ""
    calls: dict[int, dict] = {}
    thinking: cl.Step | None = None
    try:
        stream = await client.chat.completions.create(
            model=MODEL, messages=messages, stream=True, **extra
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            # Reasoning models stream their thinking in a separate field
            reasoning = getattr(delta, "reasoning", None)
            if reasoning:
                if thinking is None:
                    thinking = cl.Step(name="Thinking", type="llm")
                    await thinking.__aenter__()
                await thinking.stream_token(reasoning)
            if delta.content:
                if thinking is not None:
                    await thinking.__aexit__(None, None, None)
                    thinking = None
                text += delta.content
                await reply.stream_token(delta.content)
            # Tool calls arrive in pieces; join them by index
            for tc in delta.tool_calls or []:
                call = calls.setdefault(
                    tc.index, {"id": "", "name": "", "arguments": ""}
                )
                call["id"] = tc.id or call["id"]
                if tc.function:
                    call["name"] += tc.function.name or ""
                    call["arguments"] += tc.function.arguments or ""
    finally:
        if thinking is not None:
            await thinking.__aexit__(None, None, None)
    return text, [calls[i] for i in sorted(calls)]


@cl.on_message
async def on_message(message: cl.Message):
    history: list = cl.user_session.get("history")
    history.append({"role": "user", "content": message.content})
    start = len(history)

    settings = cl.user_session.get("settings") or {}
    search_on = settings.get("web_search", False)
    reply = cl.Message(content="")
    try:
        for round_no in range(SEARCH_MAX_ROUNDS + 1):
            extra = {"extra_body": reasoning_body(settings)}
            messages = history
            if search_on:
                extra["tools"] = TOOLS
                if round_no == SEARCH_MAX_ROUNDS:
                    # Limit reached: keep the tool listed (so the model isn't
                    # confused) but forbid calling it, and tell it to answer.
                    extra["tool_choice"] = "none"
                    messages = history + [LIMIT_NOTE]
            text, calls = await stream_round(messages, reply, extra)
            if not calls or round_no == SEARCH_MAX_ROUNDS:
                break
            history.append(
                {
                    "role": "assistant",
                    "content": text or None,
                    "tool_calls": [
                        {
                            "id": c["id"],
                            "type": "function",
                            "function": {"name": c["name"], "arguments": c["arguments"]},
                        }
                        for c in calls
                    ],
                }
            )
            for c in calls:
                history.append(
                    {"role": "tool", "tool_call_id": c["id"], "content": await run_tool_call(c)}
                )
    except Exception as e:
        # Drop half-finished tool turns so the next message starts clean
        del history[start:]
        reply.content = f"Error: {e}"
    if not reply.content:
        reply.content = "(The model returned an empty response.)"
    await reply.send()

    history.append({"role": "assistant", "content": reply.content})
