"""Nothing internal reaches the page: no tracebacks, no API key."""

import json

from researchchat import config
from researchchat.server import socket as chat_socket
from researchchat.server.events import ChatStop
from researchchat.tools import web_search
from tests.server.conftest import (
    events_until,
    open_tab,
    send_message,
    text_chunk,
    tool_call_chunk,
)

# ---- No leaks · API
# Baseline: Given a full turn with a tool step, Settings and a toast · When every event sent to the page is collected


def test_handler_crash_sends_a_generic_error(client, monkeypatch):
    # Changed: a handler raises
    # Then: error "Something went wrong; see the app log." with no traceback or file path
    # Demonstrates: failures don't expose the app's insides
    async def crash(_chat, _event) -> None:
        raise RuntimeError("secret detail in /home/user/project/file.py")

    monkeypatch.setitem(chat_socket.EVENT_HANDLERS, ChatStop, crash)
    with open_tab(client) as tab:
        tab.receive_json()
        tab.send_json({"type": "chat.stop"})
        error = tab.receive_json()

    assert error == {"type": "error", "code": "INTERNAL", "message": "Something went wrong; see the app log."}


def test_no_event_carries_the_api_key(client, model, monkeypatch):
    # Changed: nothing
    # Then: the OpenRouter key appears in no event
    # Demonstrates: the key never leaves the server
    key = config.OPENROUTER_API_KEY or "sk-or-placeholder-for-the-test"
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", key)

    async def found(args: dict) -> tuple[str, str]:
        return "3 results", "results"

    monkeypatch.setattr(web_search, "run", found)
    model.scripts += [[tool_call_chunk("web_search", {"query": "q"})], [text_chunk("Done")]]
    with open_tab(client) as tab:
        events = [tab.receive_json()]
        tab.send_json({"type": "settings.update", "values": {"show_thinking": False}})
        send_message(tab)
        events += events_until(tab, "reply.ended")
        tab.send_json({"type": "nope"})
        events.append(tab.receive_json())

    sent = json.dumps(events)
    assert key not in sent
