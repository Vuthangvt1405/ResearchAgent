"""ResearchChat entry point: Chainlit calls the @cl.on_... hooks below.

Run with: chainlit run app.py
"""

import chainlit as cl

from researchchat.config import GREETING, SYSTEM_PROMPT, TOOL_MAX_ROUNDS
from researchchat.llm import model_params, stream_round
from researchchat.progress import Progress
from researchchat.settings import build_widgets, reasoning_body
from researchchat.tools import TOOLS, run_tool_call

LIMIT_NOTE = {
    "role": "system",
    "content": (
        "Tool limit reached. Do not search or read more pages. Answer the "
        "user now using the results above, and cite the URLs you used."
    ),
}


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set(
        "history", [{"role": "system", "content": SYSTEM_PROMPT}]
    )
    widgets = build_widgets(await model_params())
    settings = await cl.ChatSettings(widgets).send() if widgets else {}
    cl.user_session.set("settings", settings)
    await cl.Message(content=GREETING).send()


@cl.on_settings_update
async def on_settings_update(settings: dict):
    cl.user_session.set("settings", settings)


@cl.on_message
async def on_message(message: cl.Message):
    history: list = cl.user_session.get("history")
    history.append({"role": "user", "content": message.content})
    start = len(history)

    settings = cl.user_session.get("settings") or {}
    tools_on = settings.get("web_search", False)
    # Create the reply before the progress group so it isn't nested inside it
    reply = cl.Message(content="")
    progress = Progress()
    try:
        # Each round: the model answers or calls tools; tool results go back in
        for round_no in range(TOOL_MAX_ROUNDS + 1):
            extra = {"extra_body": reasoning_body(settings)}
            messages = history
            if tools_on:
                extra["tools"] = TOOLS
                if round_no == TOOL_MAX_ROUNDS:
                    # Limit reached: keep the tools listed (so the model isn't
                    # confused) but forbid calling them, and tell it to answer.
                    extra["tool_choice"] = "none"
                    messages = history + [LIMIT_NOTE]
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
