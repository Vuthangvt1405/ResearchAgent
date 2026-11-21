"""Test doubles for Kaggle: a mock HTTP service that answers like the live one, and a fake listener."""

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar

import httpx

from sillytherin.workspace.kaggle import oauth
from sillytherin.workspace.kaggle.callback import CallbackResult
from sillytherin.workspace.kaggle.my_datasets import LIST_DATASETS_URL

ACCESS_TOKEN = "AT-SECRET-0001"
REFRESHED_ACCESS_TOKEN = "AT-SECRET-0002"
REFRESH_TOKEN = "RT-SECRET-0001"
CLIENT_ID = "sillytherin"
USERNAME = "ana"

Answer = Callable[[httpx.Request], httpx.Response]


def token_answer(access_token: str = ACCESS_TOKEN, refresh_token: str | None = REFRESH_TOKEN) -> dict:
    answer = {"access_token": access_token, "token_type": "Bearer", "expires_in": 10800, "username": USERNAME,
              "scope": oauth.OAUTH_SCOPE}
    if refresh_token:
        answer["refresh_token"] = refresh_token
    return answer


@dataclass
class FakeKaggle:
    """Answers register, token and revoke like Kaggle did live; any answer can be replaced per test."""

    requests: list[httpx.Request] = field(default_factory=list)
    register: Answer | None = None
    token: Answer | None = None
    revoke: Answer | None = None
    list_datasets: Answer | None = None  # "my datasets"; Kaggle answers {} for an account with none

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url).split("?")[0]
        if url == LIST_DATASETS_URL:
            return (self.list_datasets or (lambda _r: httpx.Response(200, json={})))(request)
        if url == oauth.REGISTER_URL:
            return (self.register or self._registered)(request)
        if url == oauth.TOKEN_URL:
            return (self.token or self._tokens)(request)
        if url == oauth.REVOKE_URL:
            return (self.revoke or (lambda _r: httpx.Response(200, json={})))(request)
        return httpx.Response(404)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle))

    def calls_to(self, url: str) -> list[httpx.Request]:
        return [r for r in self.requests if str(r.url).split("?")[0] == url]

    @staticmethod
    def _registered(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        return httpx.Response(200, json={"client_id": CLIENT_ID, "redirect_uris": body["redirect_uris"],
                                         "client_secret": "", "token_endpoint_auth_method": "none"})

    @staticmethod
    def _tokens(request: httpx.Request) -> httpx.Response:
        form = dict(httpx.QueryParams(request.content.decode()))
        if form.get("grant_type") == "refresh_token":
            return httpx.Response(200, json=token_answer(REFRESHED_ACCESS_TOKEN, refresh_token=None))
        return httpx.Response(200, json=token_answer())


def answer(status: int, body: dict | None = None) -> Answer:
    return lambda _request: httpx.Response(status, json=body or {})


def network_down(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("unreachable", request=request)


class FakeListener:
    """Stands in for CallbackListener: the test decides when and how the browser comes back."""

    PORT = 48123
    created: ClassVar[list["FakeListener"]] = []

    def __init__(self, expected_state: str, timeout_seconds: float):
        self.expected_state = expected_state
        self.timeout_seconds = timeout_seconds
        self.closed = False
        self._result: asyncio.Future[CallbackResult] | None = None
        FakeListener.created.append(self)

    async def start(self) -> str:
        self._result = asyncio.get_running_loop().create_future()
        return f"http://127.0.0.1:{self.PORT}/callback"

    async def wait(self) -> CallbackResult:
        assert self._result is not None
        return await self._result

    async def close(self) -> None:
        self.closed = True
        if self._result is not None and not self._result.done():
            self._result.set_result(CallbackResult("cancelled"))

    def come_back(self, result: CallbackResult) -> None:
        assert self._result is not None
        self._result.set_result(result)
