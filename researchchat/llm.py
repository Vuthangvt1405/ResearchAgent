"""Talking to OpenRouter: the client, model capabilities and streaming."""

from dataclasses import dataclass

import chainlit as cl
import httpx
from openai import AsyncOpenAI

from researchchat.config import MODEL, OPENROUTER_API_KEY, OPENROUTER_URL
from researchchat.progress import Progress

client = AsyncOpenAI(base_url=OPENROUTER_URL, api_key=OPENROUTER_API_KEY)

@dataclass(frozen=True)
class ModelInfo:
    """One OpenRouter model as the app needs it."""

    id: str
    name: str
    params: frozenset[str]


_catalog: dict[str, ModelInfo] | None = None


async def model_catalog() -> dict[str, ModelInfo]:
    """Every OpenRouter model that answers in text, fetched once per app run."""
    global _catalog
    if _catalog is None:
        try:
            async with httpx.AsyncClient(timeout=10) as http:
                resp = await http.get(f"{OPENROUTER_URL}/models")
                resp.raise_for_status()
            _catalog = parse_catalog(resp.json()["data"])
        except Exception:
            return {}  # don't cache, so the next chat retries
    return _catalog


def parse_catalog(entries: list[dict]) -> dict[str, ModelInfo]:
    """Keep the models that can write a chat answer; image- or audio-only models can't."""
    return {
        entry["id"]: ModelInfo(
            id=entry["id"],
            name=entry.get("name") or entry["id"],
            params=frozenset(entry.get("supported_parameters", [])),
        )
        for entry in entries
        if answers_in_text(entry)
    }


def answers_in_text(entry: dict) -> bool:
    """Models that don't list their outputs are taken as text models, as most are."""
    outputs = (entry.get("architecture") or {}).get("output_modalities") or ["text"]
    return "text" in outputs


async def model_params(model_id: str = MODEL) -> set[str]:
    """Which request parameters `model_id` supports; none when it is unknown or OpenRouter can't be reached."""
    model = (await model_catalog()).get(model_id)
    return set(model.params) if model else set()


async def stream_round(
    messages: list, reply: cl.Message, extra: dict, progress: Progress, model_id: str = MODEL
) -> tuple[str, list[dict]]:
    """Stream one model response into the UI.

    Thinking goes into a step inside `progress`; the answer goes into `reply`.
    Returns the text written this round and any tool calls the model made.
    """
    text = ""
    calls: dict[int, dict] = {}
    thinking: cl.Step | None = None
    try:
        stream = await client.chat.completions.create(
            model=model_id, messages=messages, stream=True, **extra
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            # Reasoning models stream their thinking in a separate field
            reasoning = getattr(delta, "reasoning", None)
            if reasoning:
                if thinking is None:
                    await progress.step_started("Thinking")
                    thinking = cl.Step(name="Thinking", type="llm")
                    await thinking.__aenter__()
                await thinking.stream_token(reasoning)
            if delta.content:
                if thinking is not None:
                    await thinking.__aexit__(None, None, None)
                    thinking = None
                if not text and progress.group is not None:
                    await progress.now("Writing answer")
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
