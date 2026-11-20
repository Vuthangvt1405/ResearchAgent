"""ResearchChat entry point: Chainlit calls the @cl.on_... hooks below
Run with: chainlit run app.py
"""

import asyncio
import os
import subprocess

import chainlit as cl
from chainlit.config import FILES_DIRECTORY
from chainlit.input_widget import InputWidget

from researchchat.config import (
    EFFORT_DEFAULT,
    EFFORT_LEVELS,
    MODEL,
    SYSTEM_PROMPT,
    TOOL_MAX_ROUNDS,
    WORKSPACES_DIR,
    check_local_host,
    check_setup,
)
from researchchat.db.engine import database_for

# Wrong Python or no API key: say how to fix it before anything else fails
check_setup()
# Create or upgrade workspaces/researchchat.db now; a damaged or newer file stops here with steps
database_for(WORKSPACES_DIR)

from researchchat.llm import (  # imported after check_setup: it needs the key checked first
    model_catalog,
    model_params,
    stream_round,
)
from researchchat.modes import (
    PickerChoices,
    Picks,
    build_modes,
    chosen_picks,
    picker_models,
)
from researchchat.progress import Progress
from researchchat.settings import (
    build_widgets,
    keep_chat_choices,
    reasoning_body,
    usable_settings,
)
from researchchat.tools import chosen_tools, run_tool_call
from researchchat.workspace import actions as notebook
from researchchat.workspace.kaggle.account import KaggleAccountStatus

# Notebook cells run code, so never serve beyond this PC (Chainlit sets this from --host)
check_local_host(os.environ.get("CHAINLIT_HOST", "127.0.0.1"))

LIMIT_NOTE = {
    "role": "system",
    "content": (
        "Tool limit reached. Do not search or read more pages. Answer the "
        "user now using the results above, and cite the URLs you used."
    ),
}

DEFAULT_PICKS = Picks(model=MODEL, effort=EFFORT_DEFAULT)

_cleaned = False


def current_picks() -> Picks:
    """This chat's Model and Effort picks, or the defaults before its first message."""
    return cl.user_session.get("picks") or DEFAULT_PICKS


async def settings_for(kaggle: KaggleAccountStatus) -> list[InputWidget]:
    """The Settings widgets for this chat's model, with the Kaggle account switch in `kaggle`'s state."""
    return build_widgets(await model_params(current_picks().model), kaggle=kaggle)


async def picker_choices() -> PickerChoices:
    """What the pickers offer: every OpenRouter text model, and the configured effort levels."""
    names = {model.id: model.name for model in (await model_catalog()).values()}
    return PickerChoices(models=picker_models(names, MODEL), levels=EFFORT_LEVELS)


async def send_pickers(picks: Picks) -> None:
    """Show the chat box pickers at this chat's picks; Effort only when the model can reason."""
    can_reason = "reasoning" in await model_params(picks.model)
    await cl.context.emitter.set_modes(build_modes(await picker_choices(), picks, can_reason))


async def follow_model_change(picks: Picks) -> None:
    """A new model can change what the chat offers: re-send the pickers and Settings for it."""
    await send_pickers(picks)
    chosen = cl.user_session.get("settings") or {}
    widgets = keep_chat_choices(await settings_for(notebook.kaggle_account.status()), chosen)
    cl.user_session.set("settings", await cl.ChatSettings(widgets).send())


notebook.settings_widgets = settings_for  # lets an account change re-send Settings to every chat


def ensure_files_dir() -> None:
    """Recreate Chainlit's .files/ if it's gone.

    Chainlit makes it once at start and deletes it when a server stops, so a
    second server run from this folder (a preview, a test run) takes it away
    from this one, and every new chat then fails with "No such file or directory".
    """
    FILES_DIRECTORY.mkdir(parents=True, exist_ok=True)


@cl.on_chat_start
async def on_chat_start():
    global _cleaned
    ensure_files_dir()
    if not _cleaned:
        # Kernel containers left by an earlier run of the app
        _cleaned = True
        asyncio.create_task(notebook.kernels.cleanup_leftovers())
        # Downloads cut off by an earlier run; dataset_download waits for this
        asyncio.create_task(notebook.datasets.startup_cleanup())

    cl.user_session.set(
        "history", [{"role": "system", "content": SYSTEM_PROMPT}]
    )
    cl.user_session.set("picks", DEFAULT_PICKS)
    await send_pickers(DEFAULT_PICKS)
    widgets = await settings_for(notebook.kaggle_account.status())
    settings = await cl.ChatSettings(widgets).send()
    cl.user_session.set("settings", settings)
    await notebook.open_for_session()


@cl.on_app_shutdown
async def on_app_shutdown() -> None:
    # Kernels hold memory until stopped; without this they run on after the app exits
    try:
        await notebook.kernels.stop_all()
    except (OSError, subprocess.TimeoutExpired):
        pass  # Docker is gone or stuck: cleanup_leftovers removes them on the next start


@cl.on_chat_end
async def on_chat_end():
    notebook.close_for_session()


@cl.on_settings_update
async def on_settings_update(settings: dict):
    previous_settings = cl.user_session.get("settings") or {}
    cl.user_session.set("settings", settings)
    await notebook.apply_kaggle_switch(previous_settings, settings)


@cl.on_message
async def on_message(message: cl.Message):
    ensure_files_dir()
    history: list = cl.user_session.get("history")
    history.append({"role": "user", "content": message.content})
    start = len(history)

    previous_picks = current_picks()
    picks = chosen_picks(message.modes, await picker_choices(), previous_picks)
    cl.user_session.set("picks", picks)
    if picks.model != previous_picks.model:
        await follow_model_change(picks)
    params = await model_params(picks.model)
    settings = usable_settings(cl.user_session.get("settings") or {}, params)
    tools = chosen_tools(settings)
    thinking = reasoning_body(
        effort=picks.effort,
        show_thinking=settings.get("show_thinking", True),
        can_reason="reasoning" in params,
    )
    # Background downloads that finished since the last turn: told to the model
    # once, for this turn only, never kept in history
    note = notebook.datasets.take_notes(cl.context.session.id)
    turn_notes = [{"role": "system", "content": note}] if note else []
    # Create the reply before the progress group so it isn't nested inside it
    reply = cl.Message(content="")
    progress = Progress()
    try:
        # Each round: the model answers or calls tools; tool results go back in
        for round_no in range(TOOL_MAX_ROUNDS + 1):
            extra = {"extra_body": thinking}
            messages = history + turn_notes
            if tools:
                extra["tools"] = tools
                if round_no == TOOL_MAX_ROUNDS:
                    # Limit reached: keep the tools listed (so the model isn't
                    # confused) but forbid calling them, and tell it to answer.
                    extra["tool_choice"] = "none"
                    messages = history + turn_notes + [LIMIT_NOTE]
            text, calls = await stream_round(messages, reply, extra, progress, model_id=picks.model)
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
