"""ResearchChat entry point: Chainlit calls the @cl.on_... hooks below.

Run with: chainlit run app.py
"""

import asyncio
import os

import chainlit as cl

from researchchat.config import GREETING, SYSTEM_PROMPT, TOOL_MAX_ROUNDS, check_local_host
from researchchat.llm import model_params, stream_round
from researchchat.progress import Progress
from researchchat.settings import build_widgets, reasoning_body
from researchchat.tools import chosen_tools, run_tool_call
from researchchat.workspace import actions as notebook

# Notebook cells run code, so never serve beyond this PC (Chainlit sets this from --host)
check_local_host(os.environ.get("CHAINLIT_HOST", "127.0.0.1"))

LIMIT_NOTE = {
    "role": "system",
    "content": (
        "Tool limit reached. Do not search or read more pages. Answer the "
        "user now using the results above, and cite the URLs you used."
    ),
}

_cleaned = False


@cl.on_chat_start
async def on_chat_start():
    global _cleaned
    if not _cleaned:
        # Kernel containers left by an earlier run of the app
        _cleaned = True
        asyncio.create_task(notebook.kernels.cleanup_leftovers())
        # Downloads cut off by an earlier run; dataset_download waits for this (NB-3)
        asyncio.create_task(notebook.datasets.startup_cleanup())

    cl.user_session.set(
        "history", [{"role": "system", "content": SYSTEM_PROMPT}]
    )
    widgets = build_widgets(await model_params())
    settings = await cl.ChatSettings(widgets).send() if widgets else {}
    cl.user_session.set("settings", settings)
    await notebook.open_for_session()
    await cl.Message(content=GREETING).send()


@cl.on_chat_end
async def on_chat_end():
    notebook.close_for_session()


@cl.on_settings_update
async def on_settings_update(settings: dict):
    cl.user_session.set("settings", settings)


@cl.on_message
async def on_message(message: cl.Message):
    history: list = cl.user_session.get("history")
    history.append({"role": "user", "content": message.content})
    start = len(history)

    settings = cl.user_session.get("settings") or {}
    tools = chosen_tools(settings)
    # Background downloads that finished since the last turn: told to the model
    # once, for this turn only, never kept in history (NB-3)
    note = notebook.datasets.take_notes(cl.context.session.id)
    turn_notes = [{"role": "system", "content": note}] if note else []
    # Create the reply before the progress group so it isn't nested inside it
    reply = cl.Message(content="")
    progress = Progress()
    try:
        # Each round: the model answers or calls tools; tool results go back in
        for round_no in range(TOOL_MAX_ROUNDS + 1):
            extra = {"extra_body": reasoning_body(settings)}
            messages = history + turn_notes
            if tools:
                extra["tools"] = tools
                if round_no == TOOL_MAX_ROUNDS:
                    # Limit reached: keep the tools listed (so the model isn't
                    # confused) but forbid calling them, and tell it to answer.
                    extra["tool_choice"] = "none"
                    messages = history + turn_notes + [LIMIT_NOTE]
            text, calls = await stream_round(messages, reply, extra, progress)
            if not calls or round_no == TOOL_MAX_ROUNDS:
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
                    {"role": "tool", "tool_call_id": c["id"], "content": await run_tool_call(c, progress)}
                )
    except Exception as e:
        # Drop half-finished tool turns so the next message starts clean
        del history[start:]
        reply.content = f"Error: {e}"
    finally:
        await progress.finish()
    if not reply.content:
        reply.content = "(The model returned an empty response.)"
    await reply.send()

    history.append({"role": "assistant", "content": reply.content})
