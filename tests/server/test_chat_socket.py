"""A chat over its WebSocket: open, stream, tools, panel, Stop, prompts, reconnect and close."""

import time

from sillytherin.tools import notebook_run, web_search
from sillytherin.workspace import actions
from tests.server.conftest import (
    HANG,
    events_until,
    next_event_after_probe,
    open_tab,
    send_message,
    text_chunk,
    tool_call_chunk,
)

# ---- Socket session · API
# Baseline: Given the app server with fake services and a socket from the app's own page · When a chat opens and sends a message


def types(events: list[dict]) -> list[str]:
    return [event["type"] for event in events]


def history_of(sessions, chat_id: str) -> list[dict]:
    return sessions.resume(chat_id).state.get("history")


def test_opening_a_chat_sends_session_ready(client):
    # Changed: nothing
    # Then: session.ready with a new chat id, the pickers, Settings and the project's panel props
    # Demonstrates: a chat opens with everything the page draws first
    with open_tab(client) as tab:
        ready = tab.receive_json()

    assert ready["type"] == "session.ready" and ready["chat_id"]
    assert ready["messages"] == []
    assert [picker["id"] for picker in ready["pickers"]] == ["model", "effort"]
    assert [switch["id"] for switch in ready["settings"]] == ["show_thinking", "web_search", "notebook", "kaggle_account"]
    assert ready["panel"]["project"]["id"] and ready["panel"]["cells"] == []


def test_a_message_streams_reply_events_in_order(client, model, sessions):
    # Changed: chat.send "hi"
    # Then: reply.started, reply.delta…, reply.ended in that order; history gained the message and the answer
    # Demonstrates: the answer streams like today
    model.scripts.append([text_chunk("Hel"), text_chunk("lo")])
    with open_tab(client) as tab:
        chat_id = tab.receive_json()["chat_id"]
        send_message(tab, "hi")
        events = events_until(tab, "reply.ended")

    assert types(events) == ["reply.started", "reply.delta", "reply.delta", "reply.ended"]
    assert events[-1]["text"] == "Hello"
    assert history_of(sessions, chat_id)[-2:] == [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "Hello"}]


def test_tool_steps_reach_the_page(client, model, monkeypatch):
    # Changed: the model calls a tool
    # Then: group.label with the step title, then step.done with its output
    # Demonstrates: tool steps are visible
    async def found(args: dict) -> tuple[str, str]:
        return "3 results", "results"

    monkeypatch.setattr(web_search, "run", found)
    model.scripts += [[tool_call_chunk("web_search", {"query": "hanoi"})], [text_chunk("Done")]]
    title = web_search.step_title({"query": "hanoi"})
    with open_tab(client) as tab:
        tab.receive_json()
        send_message(tab)
        events = events_until(tab, "reply.ended")

    labels = [e["label"] for e in events if e["type"] == "group.label"]
    assert title in labels
    assert [(e["title"], e["output"]) for e in events if e["type"] == "step.done"] == [(title, "3 results")]
    assert [e["type"] for e in events if e["type"] == "group.done"] == ["group.done"]


def test_panel_action_replies_and_pushes_to_other_tabs(client):
    # Changed: two sockets on one project; tab A sends panel.action nb_add_cell
    # Then: A gets panel.result; B gets panel.props; A gets no panel.props
    # Demonstrates: edits reach every tab, and the typing tab keeps its cursor
    with open_tab(client) as tab_a, open_tab(client) as tab_b:
        version = tab_a.receive_json()["panel"]["version"]
        tab_b.receive_json()
        tab_a.send_json({"type": "panel.action", "request_id": "r1", "name": "nb_add_cell",
                         "payload": {"version": version, "after_id": None, "type": "code"}})
        result = tab_a.receive_json()
        pushed = tab_b.receive_json()
        after_result = next_event_after_probe(tab_a)

    assert result["type"] == "panel.result" and result["request_id"] == "r1" and len(result["result"]["cells"]) == 1
    assert pushed["type"] == "panel.props" and len(pushed["props"]["cells"]) == 1
    assert after_result["type"] == "error"


def test_stop_cancels_the_turn_and_keeps_partial_text(client, model):
    # Changed: chat.stop while the reply streams
    # Then: reply.ended with the partial text; the next chat.send works
    # Demonstrates: Stop works
    model.scripts += [[text_chunk("Hel"), HANG], [text_chunk("again")]]
    with open_tab(client) as tab:
        tab.receive_json()
        send_message(tab)
        events_until(tab, "reply.delta")
        tab.send_json({"type": "chat.stop"})
        stopped = events_until(tab, "reply.ended")[-1]
        send_message(tab, "next")
        next_reply = events_until(tab, "reply.ended")[-1]

    assert stopped["text"] == "Hel"
    assert next_reply["text"] == "again"


def test_settings_update_changes_the_next_message(client, model):
    # Changed: settings.update with Web search off
    # Then: the next turn offers the model no search tools
    # Demonstrates: Settings apply to the next message
    with open_tab(client) as tab:
        tab.receive_json()
        tab.send_json({"type": "settings.update", "values": {"web_search": False}})
        send_message(tab)
        events_until(tab, "reply.ended")

    offered = model.tool_names(0)
    assert "web_search" not in offered and "read_page" not in offered and "dataset_search" not in offered
    assert "notebook_run" in offered


def test_prompt_round_trip_runs_on_run(client, model, services):
    # Changed: a tool asks and the page answers run
    # Then: ask.opened, then ask.closed; the tool ran
    # Demonstrates: Run / Skip works over the socket
    model.scripts += [[tool_call_chunk("notebook_run", {"code": "!ls"})], [text_chunk("Ran it")]]
    with open_tab(client) as tab:
        tab.receive_json()
        send_message(tab)
        asked = events_until(tab, "ask.opened")[-1]
        tab.send_json({"type": "ask.answer", "ask_id": asked["ask_id"], "choice": "run"})
        events = events_until(tab, "reply.ended")

    assert [c["id"] for c in asked["choices"]] == ["run", "skip"] and "!ls" in asked["markdown"]
    assert [e["choice"] for e in events if e["type"] == "ask.closed"] == ["run"]
    assert services.kernels.executed == ["!ls"]


def test_background_message_reaches_only_its_chat(client):
    # Changed: a download started in chat A finishes
    # Then: A gets chat.message; B gets nothing
    # Demonstrates: background news goes to the right chat
    with open_tab(client) as tab_a, open_tab(client) as tab_b:
        chat_a = tab_a.receive_json()["chat_id"]
        tab_b.receive_json()
        assert client.portal.call(actions.chats.send, chat_a, "pm25.csv finished downloading.")
        message = tab_a.receive_json()
        on_b = next_event_after_probe(tab_b)

    assert message == {"type": "chat.message", "text": "pm25.csv finished downloading."}
    assert on_b["type"] == "error"


def test_reconnect_returns_the_same_chat(client, model):
    # Changed: the socket drops and reconnects with its chat id while the app runs
    # Then: session.ready with the same chat id and history
    # Demonstrates: a short break keeps the chat
    model.scripts.append([text_chunk("Hello")])
    with open_tab(client) as tab:
        chat_id = tab.receive_json()["chat_id"]
        send_message(tab, "hi")
        events_until(tab, "reply.ended")
    with open_tab(client, chat_id) as tab:
        ready = tab.receive_json()

    assert ready["type"] == "session.ready" and ready["chat_id"] == chat_id
    assert ready["messages"] == [{"role": "user", "text": "hi"}, {"role": "assistant", "text": "Hello"}]


def test_reconnect_after_restart_opens_a_new_chat(client):
    # Changed: reconnect with a chat id the app doesn't know
    # Then: chat.closed, then session.ready with a new id
    # Demonstrates: a restart never brings back or leaks old chats
    with open_tab(client, "chat-from-before-the-restart") as tab:
        closed = tab.receive_json()
        ready = tab.receive_json()

    assert closed == {"type": "chat.closed"}
    assert ready["type"] == "session.ready" and ready["chat_id"] != "chat-from-before-the-restart"


def test_unanswered_prompt_times_out_as_skip(client, model, services, monkeypatch):
    # Changed: nobody answers a prompt within its timeout
    # Then: ask.closed with no choice; the tool didn't run
    # Demonstrates: no answer counts as Skip
    monkeypatch.setattr(notebook_run, "APPROVAL_TIMEOUT_SECONDS", 0.2)
    model.scripts += [[tool_call_chunk("notebook_run", {"code": "!ls"})], [text_chunk("Skipped")]]
    with open_tab(client) as tab:
        tab.receive_json()
        send_message(tab)
        events = events_until(tab, "reply.ended")

    assert [e["choice"] for e in events if e["type"] == "ask.closed"] == [None]
    assert services.kernels.executed == []


def test_closed_tab_is_skipped_during_a_push(client):
    # Changed: tab B closed before a panel push
    # Then: tab A still gets it; no error
    # Demonstrates: a closed tab can't break the others
    with open_tab(client) as tab_a:
        version = tab_a.receive_json()["panel"]["version"]
        with open_tab(client) as tab_b:
            tab_b.receive_json()
        tab_a.send_json({"type": "panel.action", "request_id": "r1", "name": "nb_add_cell",
                         "payload": {"version": version, "after_id": None, "type": "code"}})
        result = tab_a.receive_json()

    assert result["type"] == "panel.result" and len(result["result"]["cells"]) == 1


def test_closing_the_tab_deletes_the_chat(client, model, sessions, services):
    # Changed: the socket closes and doesn't reconnect within the grace period
    # Then: the chat's history is gone from memory and nothing was written to disk
    # Demonstrates: chats aren't kept
    secret = "a sentence only this chat ever saw"
    with open_tab(client) as tab:
        chat_id = tab.receive_json()["chat_id"]
        send_message(tab, secret)
        events_until(tab, "reply.ended")
    time.sleep(sessions.grace_seconds + 0.3)

    assert not sessions.is_open(chat_id)
    assert client.portal.call(actions.chats.send, chat_id, "anyone there?") is False
    written = [path for path in services.root.rglob("*") if path.is_file() and secret.encode() in path.read_bytes()]
    assert written == []
