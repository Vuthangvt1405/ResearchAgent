"""What a turn keeps in the chat's history, and what it never keeps."""

from types import SimpleNamespace

from sillytherin.agent.history import from_langchain, to_langchain
from sillytherin.server.socket import ChatSessions
from sillytherin.workspace import actions
from sillytherin.workspace.datasets.links import find_pasted_links
from tests.agent.conftest import history_of, ready_chat, run_one_turn
from tests.scripted_chat_model import text_chunk, tool_call_chunk

# ---- History rules · unit
# Baseline: Given a chat with one earlier exchange · When a new turn runs
EARLIER = [{"role": "user", "content": "first"}, {"role": "assistant", "content": "earlier answer"}]


def chat_with_earlier_exchange():
    chat = ready_chat()
    chat.get("history").extend(EARLIER)
    return chat


def test_successful_turn_appends_its_messages(scripted, searches):
    # Changed: nothing
    # Then: history is the old messages, the new message, the tool messages and the answer
    # Demonstrates: a finished turn is remembered in its chat
    scripted.scripts += [[tool_call_chunk("web_search", {"query": "cats"})], [text_chunk("Done")]]
    run = run_one_turn(chat_with_earlier_exchange(), "again")
    assert [(m["role"], m.get("content")) for m in history_of(run)[1:]] == [
        ("user", "first"), ("assistant", "earlier answer"), ("user", "again"), ("assistant", None),
        ("tool", "Result: https://found.example/page"), ("assistant", "Done"),
    ]


def test_error_mid_turn_rolls_back_tool_messages(scripted, searches):
    # Changed: the model fails after a tool round
    # Then: the reply says Error: …; history keeps only the message and the error reply
    # Demonstrates: a failed turn leaves no half-finished tool messages
    scripted.scripts.append([tool_call_chunk("web_search", {"query": "cats"})])
    scripted.scripts.append(None)  # not a list: the second model call fails
    run = run_one_turn(chat_with_earlier_exchange(), "again")
    assert run.answer.final.startswith("Error: ")
    assert [m["role"] for m in history_of(run)[3:]] == ["user", "assistant"]


def test_turn_note_is_sent_once_and_never_stored(scripted, monkeypatch):
    # Changed: a finished-download note is waiting
    # Then: the model saw it; it isn't in history; the next turn doesn't see it
    # Demonstrates: background news is told once
    notes = ["Download finished: iris"]
    monkeypatch.setattr(actions, "datasets", SimpleNamespace(take_notes=lambda _id: notes.pop() if notes else None))
    chat = ready_chat()
    run_one_turn(chat)
    run_one_turn(chat)
    note = {"role": "system", "content": "Download finished: iris"}
    assert note in scripted.requests[0]["messages"] and note not in scripted.requests[1]["messages"]
    assert note not in chat.get("history")


def test_only_pasted_links_are_downloadable_after_conversion(scripted, searches):
    # Changed: a link only in a tool result, not in your message
    # Then: the download is refused
    # Demonstrates: only links you pasted can be downloaded
    scripted.scripts += [[tool_call_chunk("web_search", {"query": "data"})], [text_chunk("Done")]]
    run = run_one_turn(text="get https://pasted.example/data.csv")
    assert find_pasted_links(history_of(run)) == {"https://pasted.example/data.csv"}


def test_history_round_trips_through_langchain_messages():
    # Changed: nothing
    # Then: dicts to LangChain messages and back are identical
    # Demonstrates: the conversion loses nothing
    history = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "web_search", "arguments": '{"query": "x"}'}}
        ]},
        {"role": "tool", "tool_call_id": "c1", "content": "found"},
        {"role": "assistant", "content": "answer"},
    ]
    assert from_langchain(to_langchain(history)) == history


def test_closing_a_chat_deletes_its_messages(monkeypatch, tmp_path):
    # Changed: the chat is closed
    # Then: its history is gone from memory; nothing was written to disk
    # Demonstrates: a chat lives only while its tab is open
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(actions, "close_chat", lambda _chat_id: None)
    sessions = ChatSessions()
    chat = sessions.open_new()
    chat.context.state.set("history", [{"role": "user", "content": "secret"}])
    sessions.close(chat.chat_id)
    assert sessions.resume(chat.chat_id) is None and list(tmp_path.iterdir()) == []


def test_agent_keeps_nothing_between_chats(scripted):
    # Changed: a second chat runs a turn with the same model builder
    # Then: its model call sees only its own messages
    # Demonstrates: the agent holds no memory of its own
    run_one_turn(ready_chat(), "from chat one")
    run_one_turn(ready_chat(), "from chat two")
    second = [m["content"] for m in scripted.requests[1]["messages"]]
    assert second == ["You are a test assistant.", "from chat two"]


