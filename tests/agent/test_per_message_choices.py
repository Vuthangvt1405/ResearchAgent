"""Each message uses exactly the picks and switches it was sent with."""

import asyncio

from sillytherin.agent.model import APP_TITLE, build_chat_model
from sillytherin.modes import Picks
from sillytherin.turn import model_request
from tests.agent.conftest import (
    EVERY_SWITCH_ON,
    PLAIN,
    THINKS_AND_TOOLS,
    TOOLS_ONLY,
    ready_chat,
)

SEARCH_TOOLS = {"web_search", "read_page", "dataset_search"}

# ---- Per-message choices · unit
# Baseline: Given picks model a/b, effort high, Show thinking on, a model that thinks and uses tools · When the turn builds its model and tools


def request_for(model: str = THINKS_AND_TOOLS, effort: str = "high", settings: dict | None = None):
    chat = ready_chat(settings, model, effort)
    return asyncio.run(model_request(chat, Picks(model=model, effort=effort)))


def tool_names(request) -> set[str]:
    return {tool["function"]["name"] for tool in request.tools}


def test_turn_uses_the_picked_model_and_effort(catalog):
    # Changed: nothing
    # Then: the model is a/b with reasoning {"effort": "high"}
    # Demonstrates: the picks reach OpenRouter, under the app's own name
    model = build_chat_model(request_for())
    assert (model.model_name, model.reasoning, model.streaming) == (THINKS_AND_TOOLS, {"effort": "high"}, True)
    assert (model.app_title, model.app_url) == (APP_TITLE, None)


def test_effort_off_disables_reasoning(catalog):
    # Changed: effort off
    # Then: reasoning {"enabled": False}
    # Demonstrates: Off really turns thinking off
    assert build_chat_model(request_for(effort="off")).reasoning == {"enabled": False}


def test_show_thinking_off_excludes_reasoning(catalog):
    # Changed: Show thinking off
    # Then: reasoning has exclude True; no Thinking step
    # Demonstrates: hidden thinking stays hidden
    settings = {**EVERY_SWITCH_ON, "show_thinking": False}
    assert build_chat_model(request_for(settings=settings)).reasoning == {"effort": "high", "exclude": True}


def test_model_without_tools_gets_no_tools(catalog):
    # Changed: the model can't use tools
    # Then: the agent gets no tools even with the switches on
    # Demonstrates: a model is never offered what it can't use
    assert request_for(model=PLAIN).tools == []
    assert request_for(model=TOOLS_ONLY).tools != []


def test_web_search_off_hides_search_tools(catalog):
    # Changed: Web search off
    # Then: no web_search, read_page or dataset_search
    # Demonstrates: the switches still gate the tools
    offered = tool_names(request_for(settings={**EVERY_SWITCH_ON, "web_search": False}))
    assert offered and not offered & SEARCH_TOOLS


def test_non_reasoning_model_sends_no_reasoning_field(catalog):
    # Changed: the model can't think
    # Then: no reasoning setting is sent
    # Demonstrates: no thinking request to a model that can't think
    assert build_chat_model(request_for(model=TOOLS_ONLY)).reasoning is None
