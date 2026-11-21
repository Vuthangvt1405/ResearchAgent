"""The datasets the connected Kaggle account owns, as the "My Kaggle datasets" window shows them.

The access token is used here and nowhere else: the answer carries display fields only, and the list
is sent to the asking tab, never to the chat history or the model.
"""

import logging
from dataclasses import asdict, dataclass, field
from typing import Literal, Protocol

import httpx

from sillytherin.workspace.kaggle.account import (
    SIGNED_OUT_NOTICE,
    HttpFactory,
    KaggleAccountStatus,
)

log = logging.getLogger(__name__)

LIST_DATASETS_URL = "https://api.kaggle.com/v1/datasets.DatasetApiService/ListDatasets"
ROWS_PER_PAGE = 20  # Kaggle's fixed page size; it ignores pageSize
MAX_LISTED_DATASETS = 1000  # stops a huge account, or a Kaggle answer that never ends, from paging forever
MAX_PAGES = MAX_LISTED_DATASETS // ROWS_PER_PAGE
# The owner always comes from the sign-in, never from the page: "my datasets", newest first
MY_DATASETS_REQUEST = {"group": "DATASET_SELECTION_GROUP_MY", "sortBy": "DATASET_SORT_BY_UPDATED"}
HTTP_OK = 200
REFUSED_TOKEN_STATUSES = {401, 403}

ListingState = Literal["listed", "not_connected", "signed_out", "unreachable"]


@dataclass(frozen=True)
class OwnedDataset:
    """One row of the window."""

    title: str  # first line; searched
    ref: str  # "owner/slug": second line; what a later download uses
    total_bytes: int | None  # Size column; None when Kaggle doesn't say
    licence: str | None  # Licence column, as Kaggle names it
    last_updated: str | None  # Updated column, ISO-8601 UTC


@dataclass(frozen=True)
class MyDatasetsAnswer:
    """What the window shows; rows only when listed, so a failure never leaves an old or half list."""

    state: ListingState
    username: str | None = None
    datasets: list[OwnedDataset] = field(default_factory=list)
    is_truncated: bool = False

    def to_page(self) -> dict:
        """The answer as the page receives it."""
        return asdict(self)


class AccountForListing(Protocol):
    """The two things listing needs from the Kaggle account."""

    def status(self) -> KaggleAccountStatus: ...

    async def access_token(self) -> str | None: ...


class ListingFailed(Exception):
    """Kaggle didn't give a usable list; `state` is what the window shows instead."""

    def __init__(self, state: ListingState):
        super().__init__(state)
        self.state = state


class MyKaggleDatasets:
    """Lists the connected account's own datasets; expected Kaggle trouble comes back as a state, never raised."""

    def __init__(self, account: AccountForListing, http_factory: HttpFactory):
        self.account = account
        self.http_factory = http_factory

    async def list_owned(self) -> MyDatasetsAnswer:
        token = await self.account.access_token()
        if token is None:
            return MyDatasetsAnswer(self._state_without_token())
        username = self.account.status().username or ""
        try:
            raw_rows, is_truncated = await self._read_all_pages(token)
        except ListingFailed as failure:
            return MyDatasetsAnswer(failure.state)
        datasets = [owned_dataset_from(row) for row in raw_rows if is_owned_by(row, username)]
        return MyDatasetsAnswer("listed", username, datasets, is_truncated)

    def _state_without_token(self) -> ListingState:
        status = self.account.status()
        # still connected without a token means the refresh couldn't reach Kaggle; the sign-in is kept
        if status.state == "connected":
            return "unreachable"
        if status.notice == SIGNED_OUT_NOTICE:
            return "signed_out"
        return "not_connected"

    async def _read_all_pages(self, token: str) -> tuple[list[dict], bool]:
        """Every row up to the cap; True when the cap cut the list."""
        rows: list[dict] = []
        async with self.http_factory() as http:
            for page_number in range(1, MAX_PAGES + 1):
                page_rows = await read_page(http, token, page_number)
                rows.extend(page_rows)
                if len(page_rows) < ROWS_PER_PAGE:
                    return rows, False
        return rows, True


async def read_page(http: httpx.AsyncClient, token: str, page_number: int) -> list[dict]:
    """One page of "my datasets"; raises ListingFailed for anything but a usable answer."""
    try:
        response = await http.post(
            LIST_DATASETS_URL, json={**MY_DATASETS_REQUEST, "page": page_number}, headers={"Authorization": f"Bearer {token}"}
        )
    except httpx.HTTPError as error:
        log.warning("Couldn't reach Kaggle to list datasets (%s)", type(error).__name__)
        raise ListingFailed("unreachable") from None
    if response.status_code in REFUSED_TOKEN_STATUSES:
        log.warning("Kaggle refused the sign-in when listing datasets (HTTP %s)", response.status_code)
        raise ListingFailed("signed_out")
    if response.status_code != HTTP_OK:
        log.warning("Kaggle couldn't list datasets (HTTP %s)", response.status_code)
        raise ListingFailed("unreachable")
    return rows_in(response)


def rows_in(response: httpx.Response) -> list[dict]:
    """The rows of one answer; Kaggle leaves `datasets` out when there are none."""
    try:
        body = response.json()
    except ValueError:
        body = None
    rows = body.get("datasets", []) if isinstance(body, dict) else None
    if not isinstance(rows, list):
        log.warning("Kaggle's dataset list wasn't in the expected shape")
        raise ListingFailed("unreachable")
    return [row for row in rows if isinstance(row, dict)]


def is_owned_by(row: dict, username: str) -> bool:
    ref = row.get("ref")
    if not isinstance(ref, str) or "/" not in ref:
        return False
    owner_in_ref = ref.split("/", 1)[0]
    owner_ref = row.get("ownerRef", owner_in_ref)
    return owner_in_ref.lower() == username.lower() and str(owner_ref).lower() == username.lower()


def owned_dataset_from(row: dict) -> OwnedDataset:
    ref = row["ref"]
    return OwnedDataset(
        title=text_or_none(row.get("title")) or ref,
        ref=ref,
        total_bytes=byte_count_or_none(row.get("totalBytes")),
        licence=text_or_none(row.get("licenseName")),
        last_updated=text_or_none(row.get("lastUpdated")),
    )


def text_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None


def byte_count_or_none(value: object) -> int | None:
    is_byte_count = isinstance(value, int) and not isinstance(value, bool) and value >= 0
    return value if is_byte_count else None
