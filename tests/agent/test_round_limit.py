"""At the round limit the model must answer from what it found."""

from sillytherin import turn
from sillytherin.agent.round_limit import LIMIT_NOTE
from tests.agent.conftest import run_one_turn
from tests.scripted_chat_model import text_chunk, tool_call_chunk

# ---- Round limit · unit
# Baseline: Given a fake model that always calls a tool and a limit of two rounds · When the turn runs
LIMIT = 2


def always_searching(scripted) -> None:
    calls = [[tool_call_chunk("web_search", {"query": f"q{n}"}, call_id=f"call-{n}")] for n in range(LIMIT)]
    scripted.scripts += [*calls, [text_chunk("Final")]]


def test_last_round_forbids_tools_and_asks_for_an_answer(scripted, searches, monkeypatch):
    # Changed: nothing
    # Then: the third model call has tool_choice none and the limit note; the tools ran twice
    # Demonstrates: the model must answer
    monkeypatch.setattr(turn, "TOOL_MAX_ROUNDS", LIMIT)
    always_searching(scripted)
    run_one_turn()
    last = scripted.requests[LIMIT]
    assert (last.get("tool_choice"), last["messages"][-1]) == ("none", {"role": "system", "content": LIMIT_NOTE})
    assert len(searches) == LIMIT and len(scripted.requests) == LIMIT + 1


def test_round_limit_never_raises_a_recursion_error(scripted, searches, monkeypatch):
    # Changed: nothing
    # Then: no recursion error; the reply has the final text
    # Demonstrates: LangGraph's own limit never fires first
    monkeypatch.setattr(turn, "TOOL_MAX_ROUNDS", LIMIT)
    always_searching(scripted)
    assert run_one_turn().answer.final == "Final"


def test_answer_before_the_limit_needs_no_note(scripted):
    # Changed: the model answers in round one
    # Then: no limit note is sent
    # Demonstrates: the note only appears when needed
    scripted.scripts.append([text_chunk("Quick")])
    run_one_turn()
    sent = [m for request in scripted.requests for m in request["messages"]]
    assert {"role": "system", "content": LIMIT_NOTE} not in sent and "tool_choice" not in scripted.requests[0]
