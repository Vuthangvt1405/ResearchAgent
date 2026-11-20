"""A chat writes one reply at a time."""

from tests.server.conftest import HANG, events_until, open_tab, send_message, text_chunk

# ---- One turn at a time · API
# Baseline: Given a chat whose reply is streaming · When another chat.send arrives


def test_next_message_after_the_reply_is_accepted(client, model):
    # Changed: it is sent after reply.ended
    # Then: it is handled
    # Demonstrates: the chat continues normally
    model.scripts += [[text_chunk("first")], [text_chunk("second")]]
    with open_tab(client) as tab:
        tab.receive_json()
        send_message(tab, "one")
        events_until(tab, "reply.ended")
        send_message(tab, "two")
        second = events_until(tab, "reply.ended")[-1]

    assert second["text"] == "second"


def test_second_message_while_busy_is_refused(client, model, sessions):
    # Changed: it is sent while the reply streams
    # Then: error BUSY; history unchanged; the first reply finishes
    # Demonstrates: two replies can't mix their history
    model.scripts.append([text_chunk("par"), HANG])
    with open_tab(client) as tab:
        chat_id = tab.receive_json()["chat_id"]
        send_message(tab, "one")
        events_until(tab, "reply.delta")
        send_message(tab, "two")
        busy = events_until(tab, "error")[-1]
        history_while_busy = [m["content"] for m in sessions.resume(chat_id).state.get("history") if m["role"] == "user"]
        tab.send_json({"type": "chat.stop"})
        first = events_until(tab, "reply.ended")[-1]

    assert busy["code"] == "BUSY"
    assert history_while_busy == ["one"]
    assert first["text"] == "par"
