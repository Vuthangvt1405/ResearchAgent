"""Talking to OpenRouter: the client, model capabilities and streaming."""

import chainlit as cl
import httpx
from openai import AsyncOpenAI

from researchchat.config import MODEL, OPENROUTER_API_KEY, OPENROUTER_URL
from researchchat.progress import Progress

client = AsyncOpenAI(base_url=OPENROUTER_URL, api_key=OPENROUTER_API_KEY)

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


async def stream_round(
    messages: list, reply: cl.Message, extra: dict, progress: Progress
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
