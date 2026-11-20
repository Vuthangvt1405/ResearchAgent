"""Kaggle's OAuth protocol calls, against a mock Kaggle that answers like the live service."""

import asyncio
import base64
import hashlib
import json
import urllib.parse

import httpx
import pytest

from researchchat.workspace.kaggle import oauth
from tests.kaggle.fakes import (
    ACCESS_TOKEN,
    CLIENT_ID,
    REFRESH_TOKEN,
    USERNAME,
    FakeKaggle,
    answer,
    network_down,
)

REDIRECT = "http://127.0.0.1:48123/callback"
CLIENT = oauth.OAuthClient(client_id=CLIENT_ID, redirect_uri=REDIRECT)


def run(coro):
    return asyncio.run(coro)


async def with_client(kaggle: FakeKaggle, call):
    async with kaggle.client() as http:
        return await call(http)


def reason_of(kaggle: FakeKaggle, call) -> str:
    with pytest.raises(oauth.KaggleSignInError) as raised:
        run(with_client(kaggle, call))
    return raised.value.reason


# Baseline: Given a mock Kaggle that answers register, token and revoke like the live service · When each oauth function is called


def test_pkce_pair_matches_s256() -> None:
    # Changed: — · Then: challenge is unpadded base64url SHA-256 of the verifier; verifier 43–128 chars · Demonstrates: Kaggle can check the verifier
    pkce = oauth.make_pkce_pair()
    expected = base64.urlsafe_b64encode(hashlib.sha256(pkce.verifier.encode()).digest()).decode().rstrip("=")
    assert pkce.challenge == expected
    assert 43 <= len(pkce.verifier) <= 128
    assert "=" not in pkce.challenge
    assert oauth.make_pkce_pair().verifier != pkce.verifier


def test_authorize_url_has_every_parameter() -> None:
    # Changed: — · Then: the Kaggle authorize URL with code flow, query mode, client id, redirect, scope, state, challenge and S256 · Demonstrates: the browser lands on the right page
    pkce = oauth.make_pkce_pair()
    url = oauth.build_authorize_url(CLIENT, "state-123", pkce)
    assert url.startswith("https://www.kaggle.com/api/v1/oauth2/authorize?")
    params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    assert params == {
        "response_type": "code", "response_mode": "query", "client_id": CLIENT_ID, "redirect_uri": REDIRECT,
        "scope": "resources.admin:*", "state": "state-123", "code_challenge": pkce.challenge,
        "code_challenge_method": "S256",
    }
    assert pkce.verifier not in url


def test_register_client_returns_its_id() -> None:
    # Changed: — · Then: client id is taken from Kaggle's answer; the request names the client SillyTherin · Demonstrates: the app gets its own client under the chosen name
    kaggle = FakeKaggle(register=answer(200, {"client_id": "given-by-kaggle"}))
    client = run(with_client(kaggle, lambda http: oauth.register_client(http, REDIRECT)))
    assert client == oauth.OAuthClient(client_id="given-by-kaggle", redirect_uri=REDIRECT)
    sent = json.loads(kaggle.calls_to(oauth.REGISTER_URL)[0].content)
    assert sent["client_name"] == "SillyTherin"
    assert sent["redirect_uris"] == [REDIRECT]
    assert sent["token_endpoint_auth_method"] == "none"
    assert sent["code_challenge_method"] == ["S256"]


def test_exchange_code_returns_tokens_and_username() -> None:
    # Changed: — · Then: both tokens, 10800 seconds and the username · Demonstrates: one call finishes the sign-in
    kaggle = FakeKaggle()
    pkce = oauth.make_pkce_pair()
    grant = run(with_client(kaggle, lambda http: oauth.exchange_code(http, CLIENT, "code-1", pkce)))
    assert (grant.access_token, grant.refresh_token) == (ACCESS_TOKEN, REFRESH_TOKEN)
    assert (grant.expires_in_seconds, grant.username) == (10800, USERNAME)
    form = dict(httpx.QueryParams(kaggle.calls_to(oauth.TOKEN_URL)[0].content.decode()))
    assert form == {"grant_type": "authorization_code", "code": "code-1", "code_verifier": pkce.verifier,
                    "client_id": CLIENT_ID, "redirect_uri": REDIRECT}


def test_refresh_keeps_refresh_token_when_not_rotated() -> None:
    # Changed: answer has no new refresh token · Then: the grant has no refresh token, so the caller keeps the old one · Demonstrates: matches Kaggle's behaviour
    grant = run(with_client(FakeKaggle(), lambda http: oauth.refresh_access_token(http, CLIENT_ID, REFRESH_TOKEN)))
    assert grant.refresh_token is None
    assert grant.access_token.startswith("AT-SECRET")


def test_exchange_code_refused() -> None:
    # Changed: token endpoint answers 400 · Then: refused, and the message has no response body · Demonstrates: fixed message
    kaggle = FakeKaggle(token=answer(400, {"error": "invalid_request", "error_description": "BODY-TEXT"}))
    with pytest.raises(oauth.KaggleSignInError) as raised:
        run(with_client(kaggle, lambda http: oauth.exchange_code(http, CLIENT, "c", oauth.make_pkce_pair())))
    assert raised.value.reason == "refused"
    assert "BODY-TEXT" not in str(raised.value)


def test_refresh_invalid_grant_is_signed_out() -> None:
    # Changed: 400 invalid_grant · Then: signed_out · Demonstrates: a revoked sign-in is told apart
    kaggle = FakeKaggle(token=answer(400, {"error": "invalid_grant", "error_description": "Invalid refresh token"}))
    assert reason_of(kaggle, lambda http: oauth.refresh_access_token(http, CLIENT_ID, REFRESH_TOKEN)) == "signed_out"


def test_register_network_error_is_refused() -> None:
    # Changed: the transport raises ConnectError · Then: refused · Demonstrates: Kaggle down gives a clear reason
    kaggle = FakeKaggle(register=network_down)
    assert reason_of(kaggle, lambda http: oauth.register_client(http, REDIRECT)) == "refused"


def test_token_response_without_access_token() -> None:
    # Changed: 200 without access_token · Then: refused, nothing returned · Demonstrates: a half answer isn't success
    kaggle = FakeKaggle(token=answer(200, {"refresh_token": REFRESH_TOKEN}))
    assert reason_of(kaggle, lambda http: oauth.exchange_code(http, CLIENT, "c", oauth.make_pkce_pair())) == "refused"


def test_tokens_go_only_to_kaggle_endpoints() -> None:
    # Changed: every request recorded · Then: tokens only in the token endpoint body; Bearer only on the revoke call to api.kaggle.com · Demonstrates: no token reaches another host
    kaggle = FakeKaggle()

    async def whole_flow(http: httpx.AsyncClient) -> None:
        await oauth.register_client(http, REDIRECT)
        await oauth.exchange_code(http, CLIENT, "c", oauth.make_pkce_pair())
        await oauth.refresh_access_token(http, CLIENT_ID, REFRESH_TOKEN)
        await oauth.revoke_refresh_token(http, ACCESS_TOKEN, REFRESH_TOKEN)

    run(with_client(kaggle, whole_flow))
    for request in kaggle.requests:
        url = str(request.url)
        assert ACCESS_TOKEN not in url and REFRESH_TOKEN not in url
        if "authorization" in request.headers:
            assert url == oauth.REVOKE_URL
            assert request.headers["authorization"] == f"Bearer {ACCESS_TOKEN}"
        if REFRESH_TOKEN in request.content.decode():
            assert url in (oauth.TOKEN_URL, oauth.REVOKE_URL)
    assert {str(r.url).split("/")[2] for r in kaggle.requests} == {"www.kaggle.com", "api.kaggle.com"}
