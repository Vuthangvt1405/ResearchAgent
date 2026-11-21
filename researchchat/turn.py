"""One chat turn: the user's message in, the model's streamed answer and tool steps out."""

import asyncio
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph

from researchchat.agent.history import from_langchain, to_langchain
from researchchat.agent.model import ModelRequest, build_chat_model
from researchchat.agent.round_limit import RoundLimit
from researchchat.agent.stream import stream_agent
from researchchat.agent.tool_adapter import AppToolCalls, langchain_tools
from researchchat.chat.ports import (
    AnswerView,
    Asker,
    ChatState,
    ProgressView,
    SettingsView,
)
from researchchat.chat_start import (
    HISTORY_KEY,
    PICKS_KEY,
    SETTINGS_KEY,
    current_picks,
    follow_model_change,
    picker_choices,
)
from researchchat.config import TOOL_MAX_ROUNDS
from researchchat.llm import model_params
from researchchat.modes import EFFORT_MODE_ID, MODEL_MODE_ID, Picks, chosen_picks
from researchchat.progress import Progress
from researchchat.settings import reasoning_body, usable_settings
from researchchat.tools import chosen_tools
from researchchat.workspace import actions

EMPTY_ANSWER = "(The model returned an empty response.)"


@dataclass(frozen=True)
class UserMessage:
    """What the user sent, with the picker choices that came with it."""

    text: str
    model: str  # model id from the Model picker; kept only if it is offered
    effort: str  # level from the Effort picker; kept only if it is offered


@dataclass(frozen=True)
class TurnViews:
    """Where one turn shows its work."""

    answer: AnswerView
    progress: ProgressView
    asker: Asker  # Run / Skip style prompts from the tools
    settings: SettingsView  # re-sent when the message switches to another model


class CollectedAnswer:
    """Streams to the chat and keeps the text, so a stopped turn still knows what it wrote."""

    def __init__(self, view: AnswerView) -> None:
        self.view = view
        self.text = ""

    async def stream(self, text: str) -> None:
        self.text += text
        await self.view.stream(text)

    async def finish(self, text: str) -> None:
        await self.view.finish(text)


async def run_turn(chat: ChatState, message: UserMessage, views: TurnViews) -> None:
    """Answer one message with the agent, which calls tools round by round up to the round limit.

    The chat's history gains the message and the answer; a turn that fails or is
    stopped keeps none of its half-finished tool messages.
    """
    history: list = chat.get(HISTORY_KEY)
    history.append({"role": "user", "content": message.text})
    turn_start = len(history)
    request = await model_request(chat, await apply_picks(chat, message, views.settings))
    # Background downloads that finished since the last turn: told to the model once, never kept in history
    note = actions.datasets.take_notes(chat.chat_id)
    turn_notes = [{"role": "system", "content": note}] if note else []
    answer = CollectedAnswer(views.answer)
    progress = Progress(views.progress)
    try:
        added = await stream_agent(build_agent(request, progress), to_langchain(history + turn_notes), answer, progress)
        history.extend(from_langchain(tool_round_messages(added)))
        final_text = answer.text
    except asyncio.CancelledError:
        # Stop: keep what was written, drop the half-finished tool turns
        del history[turn_start:]
        final_text = answer.text
    except Exception as e:  # noqa: BLE001 - any model or tool failure ends the turn with its reason
        del history[turn_start:]
        final_text = f"Error: {e}"
    finally:
        await progress.finish()
    final_text = final_text or EMPTY_ANSWER
    await views.answer.finish(final_text)
    history.append({"role": "assistant", "content": final_text})


async def apply_picks(chat: ChatState, message: UserMessage, settings_view: SettingsView) -> Picks:
    """The message's picks become the chat's; a new model re-sends the pickers and Settings."""
    previous = current_picks(chat)
    sent = {MODEL_MODE_ID: message.model, EFFORT_MODE_ID: message.effort}
    picks = chosen_picks(sent, await picker_choices(), previous)
    chat.set(PICKS_KEY, picks)
    if picks.model != previous.model:
        await follow_model_change(chat, settings_view, actions.kaggle_account.status())
    return picks


async def model_request(chat: ChatState, picks: Picks) -> ModelRequest:
    params = await model_params(picks.model)
    settings = usable_settings(chat.get(SETTINGS_KEY) or {}, params)
    thinking = reasoning_body(
        effort=picks.effort,
        show_thinking=settings.get("show_thinking", True),
        can_reason="reasoning" in params,
    )
    return ModelRequest(model=picks.model, tools=chosen_tools(settings), thinking=thinking)


def build_agent(request: ModelRequest, progress: Progress) -> CompiledStateGraph:
    middleware = [AppToolCalls(progress), RoundLimit(TOOL_MAX_ROUNDS)]
    return create_agent(build_chat_model(request), tools=langchain_tools(request.tools), middleware=middleware)


def tool_round_messages(added: list[BaseMessage]) -> list[BaseMessage]:
    """The tool calls and their results; the answer itself is stored as the full streamed text."""
    return [m for m in added if isinstance(m, ToolMessage) or (isinstance(m, AIMessage) and m.tool_calls)]
