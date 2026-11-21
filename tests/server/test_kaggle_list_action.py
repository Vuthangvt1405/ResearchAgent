"""The list action over the chat socket: answered to the asking tab, never into the chat."""

import json

import pytest

from sillytherin.server.socket import GENERIC_FAILURE
from sillytherin.workspace import actions
from sillytherin.workspace.kaggle.my_datasets import MyDatasetsAnswer, OwnedDataset
from tests.server.conftest import open_tab

ANAS_LIST = MyDatasetsAnswer(
    "listed", "ana", [OwnedDataset("Vietnam air quality, daily", "ana/vietnam-air-quality-daily", 48_000_000, "CC BY 4.0", "2026-11-12T08:30:00Z")]
)
SECRET_DETAIL = "secret detail from deep inside"


class FakeLister:
    def __init__(self, answer: MyDatasetsAnswer | None = None, failure: Exception | None = None):
        self._answer = answer
        self._failure = failure

    async def list_owned(self) -> MyDatasetsAnswer:
        if self._failure is not None:
            raise self._failure
        assert self._answer is not None
        return self._answer


def ask_for_the_list(tab) -> dict:
    tab.receive_json()  # session.ready
    tab.send_json({"type": "panel.action", "request_id": "list-1", "name": "kg_list_my_datasets", "payload": {}})
    return tab.receive_json()


# ---- The list action answers the asking tab · API
# Baseline: Given one open chat whose Kaggle lister is a fake that answers ana's datasets · When the page sends the list action


@pytest.fixture
def anas_lister(monkeypatch) -> None:
    monkeypatch.setattr(actions, "my_kaggle_datasets", FakeLister(ANAS_LIST))


def test_the_list_action_answers_this_tab_with_the_list(client, anas_lister) -> None:
    # Changed: nothing
    # Then: a panel result with the same request id and the lister's answer as sent
    # Demonstrates: the window gets the list through the existing panel channel
    with open_tab(client) as tab:
        reply = ask_for_the_list(tab)

    assert reply["type"] == "panel.result" and reply["request_id"] == "list-1"
    assert reply["result"] == ANAS_LIST.to_page()


def test_a_surprise_failure_in_listing_answers_with_a_generic_error(client, monkeypatch) -> None:
    # Changed: the fake lister raises an unexpected error with a secret detail
    # Then: an INTERNAL error "Something went wrong; see the app log."; the detail isn't sent
    # Demonstrates: no internals leak to the page
    monkeypatch.setattr(actions, "my_kaggle_datasets", FakeLister(failure=RuntimeError(SECRET_DETAIL)))
    with open_tab(client) as tab:
        reply = ask_for_the_list(tab)

    # panel actions report a rejection inside their result, like every other panel action
    assert reply["type"] == "panel.result"
    assert reply["result"]["error"] == {"code": "INTERNAL", "message": GENERIC_FAILURE}
    assert SECRET_DETAIL not in json.dumps(reply)


# ---- The assistant is never sent the list · security


def test_listing_adds_nothing_to_the_chat_history(client, model, sessions, anas_lister) -> None:
    # Changed: nothing
    # Then: the chat history and the scripted model's calls are unchanged after the action
    # Demonstrates: the list stays between the window and the server
    with open_tab(client) as tab:
        chat_id = tab.receive_json()["chat_id"]
        history_before = sessions.resume(chat_id).state.get("history")
        tab.send_json({"type": "panel.action", "request_id": "list-1", "name": "kg_list_my_datasets", "payload": {}})
        tab.receive_json()
        history_after = sessions.resume(chat_id).state.get("history")

    assert history_after == history_before
    assert "vietnam-air-quality" not in json.dumps(history_after)
    assert model.requests == []
