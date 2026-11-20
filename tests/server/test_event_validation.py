"""Every page event is checked before any handler runs."""

import json

import pytest
from starlette.websockets import WebSocketDisconnect

from researchchat import config
from researchchat.server.events import MAX_FRAME_BYTES, MAX_MESSAGE_CHARS
from tests.server.conftest import events_until, open_tab, send_message

# ---- Event validation · API
# Baseline: Given an open chat · When it sends a valid chat.send


def history_length(sessions, chat_id: str) -> int:
    return len(sessions.resume(chat_id).state.get("history"))


def refused(tab, frame: str) -> dict:
    tab.send_text(frame)
    return tab.receive_json()


def chat_send(**fields) -> str:
    return json.dumps({"type": "chat.send", "text": "hi", "model": config.MODEL, "effort": "default", **fields})


def test_valid_message_is_handled(client):
    # Changed: nothing
    # Then: reply events
    # Demonstrates: valid events work
    with open_tab(client) as tab:
        tab.receive_json()
        send_message(tab)
        assert events_until(tab, "reply.ended")[-1]["text"] == "ok"


def test_extra_fields_are_dropped(client, model):
    # Changed: an extra project_id field
    # Then: handled; the chat's own project is used
    # Demonstrates: the page can't pick the project
    with open_tab(client) as tab:
        project = tab.receive_json()["panel"]["project"]["id"]
        tab.send_text(chat_send(project_id="someone-elses-project"))
        events_until(tab, "reply.ended")
        tab.send_json({"type": "panel.action", "request_id": "r1", "name": "nb_list_projects", "payload": {}})
        listed = tab.receive_json()

    assert listed["result"]["current"] == project


def test_unknown_event_type_is_refused(client, model):
    # Changed: type "nope"
    # Then: error BAD_EVENT; nothing ran
    # Demonstrates: unknown events never reach a handler
    with open_tab(client) as tab:
        tab.receive_json()
        error = refused(tab, json.dumps({"type": "nope", "text": "hi"}))

    assert error["type"] == "error" and error["code"] == "BAD_EVENT"
    assert model.requests == []


def refused_messages_leave_history_alone(client, model, sessions, name, frame):
    with open_tab(client) as tab:
        chat_id = tab.receive_json()["chat_id"]
        error = refused(tab, frame)
        assert error["code"] == "BAD_EVENT", name
        assert history_length(sessions, chat_id) == 1 and model.requests == [], name


def test_event_with_missing_field_is_refused(client, model, sessions):
    # Changed: chat.send without text
    # Then: error BAD_EVENT; history unchanged
    # Demonstrates: incomplete events are refused
    refused_messages_leave_history_alone(
        client, model, sessions, "missing field", json.dumps({"type": "chat.send", "model": config.MODEL, "effort": "default"})
    )


def test_event_with_wrong_type_is_refused(client, model, sessions):
    # Changed: text is the number 5
    # Then: error BAD_EVENT; history unchanged
    # Demonstrates: values are never converted
    refused_messages_leave_history_alone(client, model, sessions, "wrong type", chat_send(text=5))


def test_text_over_the_limit_is_refused(client, model, sessions):
    # Changed: 100 001 characters of text
    # Then: error BAD_EVENT; history unchanged
    # Demonstrates: message size is capped
    refused_messages_leave_history_alone(client, model, sessions, "too long", chat_send(text="x" * (MAX_MESSAGE_CHARS + 1)))


def test_not_json_is_refused(client):
    # Changed: the frame "{"
    # Then: error BAD_EVENT; the socket stays open
    # Demonstrates: a broken frame doesn't kill the chat
    with open_tab(client) as tab:
        tab.receive_json()
        error = refused(tab, "{")
        send_message(tab)
        reply = events_until(tab, "reply.ended")[-1]

    assert error["code"] == "BAD_EVENT"
    assert reply["text"] == "ok"


def test_frame_over_one_megabyte_closes_the_socket(client):
    # Changed: a frame of 1 MB and 1 byte
    # Then: close 1009
    # Demonstrates: huge frames can't exhaust memory
    with open_tab(client) as tab:
        tab.receive_json()
        tab.send_text("x" * (MAX_FRAME_BYTES + 1))
        with pytest.raises(WebSocketDisconnect) as closed:
            tab.receive_json()

    assert closed.value.code == 1009


def test_panel_action_outside_the_allow_list_is_refused(client, services):
    # Changed: panel.action named nb_drop_all
    # Then: panel.result with error BAD_PAYLOAD; notebook unchanged
    # Demonstrates: today's allow-list still guards the panel
    with open_tab(client) as tab:
        before = tab.receive_json()["panel"]
        tab.send_json({"type": "panel.action", "request_id": "r1", "name": "nb_drop_all", "payload": {}})
        result = tab.receive_json()["result"]

    assert result["error"]["code"] == "BAD_PAYLOAD"
    assert (result["version"], result["cells"]) == (before["version"], before["cells"])
