"""The connected account's own Kaggle datasets, as the "My Kaggle datasets" window gets them."""

import asyncio
import json
import logging
from dataclasses import dataclass

import httpx
import pytest

from sillytherin.workspace import actions
from sillytherin.workspace.kaggle import oauth
from sillytherin.workspace.kaggle.my_datasets import (
    LIST_DATASETS_URL,
    MAX_LISTED_DATASETS,
    ROWS_PER_PAGE,
    MyDatasetsAnswer,
    MyKaggleDatasets,
    OwnedDataset,
)
from sillytherin.workspace.kaggle.token_file import SavedSignIn
from tests.kaggle.fakes import (
    ACCESS_TOKEN,
    REFRESH_TOKEN,
    REFRESHED_ACCESS_TOKEN,
    USERNAME,
    Answer,
    FakeKaggle,
    answer,
    network_down,
)
from tests.kaggle.test_kaggle_account import SAVED, Harness
from tests.kaggle.test_kaggle_privacy import ALLOWED_KAGGLE_URLS

TOKENS = (ACCESS_TOKEN, REFRESHED_ACCESS_TOKEN, REFRESH_TOKEN)
UPDATED = "2026-11-12T08:30:00Z"


def run(coro):
    return asyncio.run(coro)


def kaggle_row(number: int, owner: str = USERNAME) -> dict:
    """One row as Kaggle's list sends it, extras included."""
    return {"ref": f"{owner}/data-{number}", "ownerRef": owner, "title": f"Data {number}", "totalBytes": 1000 + number,
            "licenseName": "CC0: Public Domain", "lastUpdated": UPDATED, "id": 90000 + number, "url": f"https://www.kaggle.com/datasets/{owner}/data-{number}",
            "ownerName": "Ana", "voteCount": 3}


def page_answers(*pages: list[dict]) -> Answer:
    """Kaggle answering each requested page number; pages past the end are empty ({}, as Kaggle answers)."""

    def handle(request: httpx.Request) -> httpx.Response:
        page_number = json.loads(request.content)["page"]
        rows = pages[page_number - 1] if page_number <= len(pages) else []
        return httpx.Response(200, json={"datasets": rows} if rows else {})

    return handle


def full_page(first_number: int) -> list[dict]:
    return [kaggle_row(first_number + offset) for offset in range(ROWS_PER_PAGE)]


def list_requests(kaggle: FakeKaggle) -> list[httpx.Request]:
    return kaggle.calls_to(LIST_DATASETS_URL)


@dataclass
class Listing:
    harness: Harness
    lister: MyKaggleDatasets

    @property
    def kaggle(self) -> FakeKaggle:
        return self.harness.kaggle

    def answer(self) -> MyDatasetsAnswer:
        return run(self.lister.list_owned())


# ---- The server lists the account's own datasets · unit
# Baseline: Given a saved sign-in for ana · When Kaggle answers one short page with two datasets owned by ana


@pytest.fixture
def listing_harness(tmp_path):
    def build(list_datasets: Answer | None = None, token: Answer | None = None, saved: SavedSignIn | None = SAVED) -> Listing:
        kaggle = FakeKaggle(token=token, list_datasets=list_datasets or page_answers([kaggle_row(1), kaggle_row(2)]))
        harness = Harness(tmp_path, kaggle=kaggle, saved=saved)
        return Listing(harness, MyKaggleDatasets(harness.service, kaggle.client))

    return build


def test_lists_the_accounts_own_datasets_with_their_details(listing_harness) -> None:
    # Changed: nothing
    # Then: state listed, username ana, both rows with title, ref, total_bytes, licence, last_updated, in Kaggle's order
    # Demonstrates: what the window shows comes straight from the account
    result = listing_harness().answer()

    assert result.state == "listed" and result.username == USERNAME and result.is_truncated is False
    assert result.datasets == [
        OwnedDataset(f"Data {n}", f"{USERNAME}/data-{n}", 1000 + n, "CC0: Public Domain", UPDATED) for n in (1, 2)
    ]


def test_reads_every_page_until_kaggle_has_no_more(listing_harness) -> None:
    # Changed: two full pages of 20 rows, then a short page
    # Then: every row, three list requests
    # Demonstrates: a long account isn't cut at the first page
    listing = listing_harness(page_answers(full_page(1), full_page(21), [kaggle_row(41)]))
    result = listing.answer()

    assert [d.ref for d in result.datasets] == [f"{USERNAME}/data-{n}" for n in range(1, 42)]
    assert [json.loads(r.content)["page"] for r in list_requests(listing.kaggle)] == [1, 2, 3]


def test_an_account_with_no_datasets_gets_an_empty_list(listing_harness) -> None:
    # Changed: Kaggle answers {} (how it really answers an empty account)
    # Then: state listed, no rows
    # Demonstrates: an empty account shows the no-datasets line, not an error
    result = listing_harness(answer(200, {})).answer()

    assert (result.state, result.datasets) == ("listed", [])


def test_missing_details_come_back_empty_not_made_up(listing_harness) -> None:
    # Changed: a row without licenseName and totalBytes
    # Then: licence and total_bytes are None
    # Demonstrates: the window never invents a size or licence
    bare = {key: value for key, value in kaggle_row(1).items() if key not in ("licenseName", "totalBytes")}
    result = listing_harness(page_answers([bare])).answer()

    assert (result.datasets[0].licence, result.datasets[0].total_bytes) == (None, None)


def test_stops_at_the_listing_cap_and_says_so(listing_harness) -> None:
    # Changed: Kaggle keeps answering full pages
    # Then: 1000 rows, is_truncated, 50 list requests
    # Demonstrates: a huge account or an endless answer can't keep the app paging forever
    endless = lambda request: httpx.Response(200, json={"datasets": full_page(json.loads(request.content)["page"] * 100)})
    listing = listing_harness(endless)
    result = listing.answer()

    assert len(result.datasets) == MAX_LISTED_DATASETS and result.is_truncated is True
    assert len(list_requests(listing.kaggle)) == MAX_LISTED_DATASETS // ROWS_PER_PAGE


def test_no_account_says_not_connected_and_never_calls_kaggle(listing_harness) -> None:
    # Changed: no saved sign-in
    # Then: state not_connected, no rows, no list request
    # Demonstrates: the window offers Connect without asking Kaggle anything
    listing = listing_harness(saved=None)
    result = listing.answer()

    assert (result.state, result.datasets, result.username) == ("not_connected", [], None)
    assert list_requests(listing.kaggle) == []


def test_a_refused_sign_in_says_signed_out(listing_harness) -> None:
    # Changed: the token refresh answers invalid_grant
    # Then: state signed_out, no rows, no list request; the account is forgotten as on any refused refresh
    # Demonstrates: a sign-in Kaggle no longer accepts asks you to connect again
    listing = listing_harness(token=answer(400, {"error": oauth.INVALID_GRANT}))
    result = listing.answer()

    assert (result.state, result.datasets) == ("signed_out", [])
    assert list_requests(listing.kaggle) == []
    assert listing.harness.file.load() is None


def test_kaggle_down_during_refresh_says_unreachable(listing_harness) -> None:
    # Changed: the token refresh can't connect
    # Then: state unreachable, no rows; the saved sign-in is kept
    # Demonstrates: network trouble doesn't sign you out
    listing = listing_harness(token=network_down)
    result = listing.answer()

    assert (result.state, result.datasets) == ("unreachable", [])
    assert listing.harness.file.load() is not None


def test_a_list_timeout_says_unreachable(listing_harness) -> None:
    # Changed: the list request times out
    # Then: state unreachable, no rows
    # Demonstrates: a slow Kaggle shows Try again
    def too_slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    result = listing_harness(too_slow).answer()

    assert (result.state, result.datasets) == ("unreachable", [])


def test_a_list_server_error_says_unreachable(listing_harness) -> None:
    # Changed: the list request answers 500
    # Then: state unreachable, no rows
    # Demonstrates: a Kaggle outage shows Try again
    result = listing_harness(answer(500)).answer()

    assert (result.state, result.datasets) == ("unreachable", [])


def test_kaggle_refusing_the_token_for_the_list_says_signed_out(listing_harness) -> None:
    # Changed: the list request answers 401
    # Then: state signed_out, no rows; the saved sign-in is kept
    # Demonstrates: a refused token asks you to connect again without deleting anything
    listing = listing_harness(answer(401))
    result = listing.answer()

    assert (result.state, result.datasets) == ("signed_out", [])
    assert listing.harness.file.load() is not None


def test_a_broken_answer_says_unreachable(listing_harness) -> None:
    # Changed: 200 with a body that isn't JSON, or datasets that isn't a list
    # Then: state unreachable, no rows
    # Demonstrates: bad data never shows as an empty account
    not_json = listing_harness(lambda _r: httpx.Response(200, text="<html>busy</html>")).answer()
    not_a_list = listing_harness(answer(200, {"datasets": "oops"})).answer()

    assert (not_json.state, not_json.datasets) == ("unreachable", [])
    assert (not_a_list.state, not_a_list.datasets) == ("unreachable", [])


def test_a_failure_on_a_later_page_returns_no_partial_list(listing_harness) -> None:
    # Changed: page 1 full, page 2 answers 500
    # Then: state unreachable, no rows
    # Demonstrates: the window never shows half a list
    def second_page_fails(request: httpx.Request) -> httpx.Response:
        if json.loads(request.content)["page"] == 1:
            return httpx.Response(200, json={"datasets": full_page(1)})
        return httpx.Response(500)

    result = listing_harness(second_page_fails).answer()

    assert (result.state, result.datasets) == ("unreachable", [])


# ---- The Kaggle token stays on the server · security
# Baseline: as above, with every log line captured


def shown_text(results: list[MyDatasetsAnswer], caplog) -> str:
    return " ".join([json.dumps(r.to_page()) for r in results] + [record.getMessage() for record in caplog.records])


def test_listing_keeps_every_token_out_of_the_answer_and_logs(listing_harness, caplog) -> None:
    # Changed: nothing
    # Then: no access or refresh token in the answer's JSON or in any log line
    # Demonstrates: the key never reaches the page, the model or the log
    caplog.set_level(logging.DEBUG)
    result = listing_harness().answer()

    shown = shown_text([result], caplog)
    assert result.state == "listed"
    assert not any(token in shown for token in TOKENS)


def test_a_failed_listing_keeps_every_token_out_of_the_answer_and_logs(listing_harness, caplog) -> None:
    # Changed: the list request answers 401, then 500, then times out
    # Then: no token anywhere in the answers or logs
    # Demonstrates: error paths don't log headers
    caplog.set_level(logging.DEBUG)

    def too_slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    results = [listing_harness(failure).answer() for failure in (answer(401), answer(500), too_slow)]

    shown = shown_text(results, caplog)
    assert [r.state for r in results] == ["signed_out", "unreachable", "unreachable"]
    assert not any(token in shown for token in TOKENS)


def test_the_token_goes_only_to_the_kaggle_list_address(listing_harness) -> None:
    # Changed: nothing; the requests are inspected
    # Then: every request carrying Authorization goes to an allowed Kaggle address; the list address is fixed
    # Demonstrates: the token can't be sent anywhere else
    listing = listing_harness()
    listing.answer()

    authorised = [r for r in listing.kaggle.requests if "authorization" in r.headers]
    assert authorised and {str(r.url).split("?")[0] for r in authorised} <= ALLOWED_KAGGLE_URLS
    assert {str(r.url) for r in list_requests(listing.kaggle)} == {LIST_DATASETS_URL}


# ---- Only the account's own datasets · security


def test_datasets_owned_by_someone_else_are_left_out(listing_harness) -> None:
    # Changed: Kaggle's answer also holds a dataset owned by bob
    # Then: only ana's rows
    # Demonstrates: even a Kaggle surprise can't show someone else's data
    result = listing_harness(page_answers([kaggle_row(1), kaggle_row(2, owner="bob")])).answer()

    assert [d.ref for d in result.datasets] == [f"{USERNAME}/data-1"]


def test_the_page_cannot_choose_whose_datasets_are_listed(listing_harness, monkeypatch) -> None:
    # Changed: the action payload carries user bob and group public
    # Then: the body sent to Kaggle is the fixed "my datasets" body; the answer is ana's
    # Demonstrates: the page can't ask for another account's datasets
    listing = listing_harness()
    monkeypatch.setattr(actions, "my_kaggle_datasets", listing.lister)

    result = run(actions.dispatch(actions.service, None, "kg_list_my_datasets", {"user": "bob", "group": "public"}))

    bodies = [json.loads(r.content) for r in list_requests(listing.kaggle)]
    assert bodies == [{"group": "DATASET_SELECTION_GROUP_MY", "sortBy": "DATASET_SORT_BY_UPDATED", "page": 1}]
    assert result["username"] == USERNAME and [d["ref"] for d in result["datasets"]] == [f"{USERNAME}/data-1", f"{USERNAME}/data-2"]
