"""Only the chat that opened a prompt can answer it, once, with an offered choice."""

from researchchat.tools import notebook_run
from tests.server.conftest import (
    events_until,
    open_tab,
    send_message,
    text_chunk,
    tool_call_chunk,
)

# ---- Prompt ownership · API
# Baseline: Given chat A has an open Run / Skip prompt · When an answer arrives


def ask_to_run(model, tab) -> str:
    """Make the model ask to run risky code in this tab; returns the prompt id."""
    model.scripts += [[tool_call_chunk("notebook_run", {"code": "!ls"})], [text_chunk("Done")]]
    send_message(tab)
    return events_until(tab, "ask.opened")[-1]["ask_id"]


def answer(tab, ask_id: str, choice: str = "run") -> None:
    tab.send_json({"type": "ask.answer", "ask_id": ask_id, "choice": choice})


def test_owner_answer_is_accepted(client, model, services):
    # Changed: A answers run with its own prompt id
    # Then: the tool runs
    # Demonstrates: the owner's answer counts
    with open_tab(client) as tab:
        tab.receive_json()
        answer(tab, ask_to_run(model, tab))
        events_until(tab, "reply.ended")

    assert services.kernels.executed == ["!ls"]


def test_answer_from_another_chat_is_refused(client, model, services):
    # Changed: chat B sends A's prompt id
    # Then: error UNKNOWN_ASK; the tool didn't run; A's prompt stays open
    # Demonstrates: one chat can't approve another's code
    with open_tab(client) as tab_a, open_tab(client) as tab_b:
        tab_a.receive_json()
        tab_b.receive_json()
        ask_id = ask_to_run(model, tab_a)
        answer(tab_b, ask_id)
        refused = tab_b.receive_json()
        ran_before_owner_answered = list(services.kernels.executed)
        answer(tab_a, ask_id)
        events_until(tab_a, "reply.ended")

    assert refused["code"] == "UNKNOWN_ASK"
    assert ran_before_owner_answered == []
    assert services.kernels.executed == ["!ls"]


def test_answer_to_a_closed_prompt_is_refused(client, model, services, monkeypatch):
    # Changed: the answer comes after the timeout
    # Then: error UNKNOWN_ASK; the tool didn't run
    # Demonstrates: a late answer can't run skipped code
    monkeypatch.setattr(notebook_run, "APPROVAL_TIMEOUT_SECONDS", 0.2)
    with open_tab(client) as tab:
        tab.receive_json()
        ask_id = ask_to_run(model, tab)
        events_until(tab, "reply.ended")
        answer(tab, ask_id)
        refused = tab.receive_json()

    assert refused["code"] == "UNKNOWN_ASK"
    assert services.kernels.executed == []


def test_second_answer_is_refused(client, model, services):
    # Changed: the same prompt id is answered twice
    # Then: the second gets error UNKNOWN_ASK; the tool ran once
    # Demonstrates: an answer can't be replayed
    with open_tab(client) as tab:
        tab.receive_json()
        ask_id = ask_to_run(model, tab)
        answer(tab, ask_id)
        events_until(tab, "reply.ended")
        answer(tab, ask_id)
        refused = tab.receive_json()

    assert refused["code"] == "UNKNOWN_ASK"
    assert services.kernels.executed == ["!ls"]


def test_unoffered_choice_is_refused(client, model, services):
    # Changed: the choice delete_all
    # Then: error BAD_EVENT; the prompt stays open
    # Demonstrates: only offered choices count
    with open_tab(client) as tab:
        tab.receive_json()
        ask_id = ask_to_run(model, tab)
        answer(tab, ask_id, "delete_all")
        refused = tab.receive_json()
        answer(tab, ask_id, "run")
        events_until(tab, "reply.ended")

    assert refused["code"] == "BAD_EVENT"
    assert services.kernels.executed == ["!ls"]
