"""Conversations go only to OpenRouter: no tracing service gets them."""

from tests.agent.conftest import run_one_turn

# ---- No tracing · unit
# Baseline: Given the tracing environment variables unset · When a turn's agent is built


def test_agent_sends_nothing_to_tracing_services(scripted, monkeypatch):
    # Changed: LangSmith tracing switched on in the environment
    # Then: tracing is off while the model is called
    # Demonstrates: conversations stay on this PC and OpenRouter
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-not-a-key")
    run_one_turn()
    assert scripted.tracing_seen == [False]
