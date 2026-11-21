"""Kaggle's OAuth sign-in protocol: PKCE, client registration, tokens, refresh and revoke.

Only small functions over an injected httpx client; no state is kept here.
Kaggle offers one scope, resources.admin:* (the whole account), so this app
only ever reads with it; the one other call it makes is cancelling its own sign-in.
"""

import base64
import hashlib
import secrets
import urllib.parse
from dataclasses import dataclass, field
from typing import Literal

import httpx

OAUTH_CLIENT_NAME = "SillyTherin"  # what Kaggle's approval page and kaggle.com → Settings show
OAUTH_SCOPE = "resources.admin:*"  # the only scope Kaggle's discovery document lists
AUTHORIZE_URL = "https://www.kaggle.com/api/v1/oauth2/authorize"
TOKEN_URL = "https://www.kaggle.com/api/v1/oauth2/token"
REGISTER_URL = "https://www.kaggle.com/api/v1/oauth2/register"
REVOKE_URL = "https://api.kaggle.com/v1/users.AccountService/ExpireApiToken"
REVOKE_REASON = "Disconnected in SillyTherin"
PKCE_VERIFIER_BYTES = 64  # token_urlsafe(64) gives 86 characters; PKCE allows 43–128
INVALID_GRANT = "invalid_grant"
HTTP_OK = 200

SignInFailure = Literal["cancelled", "timed_out", "refused", "signed_out", "revoke_unreachable"]


@dataclass(frozen=True)
class OAuthClient:
    """The app's registered Kaggle client and where Kaggle sends the browser back to."""

    client_id: str
    redirect_uri: str


@dataclass(frozen=True)
class PkcePair:
    """A random verifier the app keeps, and its SHA-256 challenge that goes in the browser link."""

    verifier: str = field(repr=False)
    challenge: str


@dataclass(frozen=True)
class TokenGrant:
    """What Kaggle's token endpoint answered. Lives in memory only."""

    access_token: str = field(repr=False)
    refresh_token: str | None = field(repr=False)
    expires_in_seconds: int
    username: str | None


class KaggleSignInError(Exception):
    """Kaggle refused or didn't finish a sign-in step; `reason` picks the fixed message shown to the user."""

    def __init__(self, reason: SignInFailure):
        super().__init__(reason)
        self.reason = reason


def make_pkce_pair() -> PkcePair:
    verifier = secrets.token_urlsafe(PKCE_VERIFIER_BYTES)
    return PkcePair(verifier=verifier, challenge=s256_challenge(verifier))


def s256_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def build_authorize_url(client: OAuthClient, state: str, pkce: PkcePair) -> str:
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "response_mode": "query",
            "client_id": client.client_id,
            "redirect_uri": client.redirect_uri,
            "scope": OAUTH_SCOPE,
            "state": state,
            "code_challenge": pkce.challenge,
            "code_challenge_method": "S256",
        },
        quote_via=urllib.parse.quote,
    )
    return f"{AUTHORIZE_URL}?{query}"


async def register_client(http: httpx.AsyncClient, redirect_uri: str) -> OAuthClient:
    registration = {
        "client_name": OAUTH_CLIENT_NAME,
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_method": "none",
        "scope": OAUTH_SCOPE,
        "code_challenge_method": ["S256"],
    }
    answer = await _post_or_refuse(http, REGISTER_URL, json=registration)
    client_id = answer.get("client_id") or answer.get("clientId")
    if not isinstance(client_id, str) or not client_id:
        raise KaggleSignInError("refused")
    return OAuthClient(client_id=client_id, redirect_uri=redirect_uri)


async def exchange_code(http: httpx.AsyncClient, client: OAuthClient, code: str, pkce: PkcePair) -> TokenGrant:
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": pkce.verifier,
        "client_id": client.client_id,
        "redirect_uri": client.redirect_uri,
    }
    return token_grant_from(await _post_or_refuse(http, TOKEN_URL, data=form))


async def refresh_access_token(http: httpx.AsyncClient, client_id: str, refresh_token: str) -> TokenGrant:
    form = {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id}
    try:
        response = await http.post(TOKEN_URL, data=form)
    except httpx.HTTPError:
        raise KaggleSignInError("refused") from None
    if response.status_code != HTTP_OK:
        raise KaggleSignInError("signed_out" if _is_invalid_grant(response) else "refused")
    return token_grant_from(_json_or_empty(response))


async def revoke_refresh_token(http: httpx.AsyncClient, access_token: str, refresh_token: str) -> None:
    try:
        response = await http.post(
            REVOKE_URL,
            json={"token": refresh_token, "reason": REVOKE_REASON},
            headers={"Authorization": f"Bearer {access_token}"},
        )
    except httpx.HTTPError:
        raise KaggleSignInError("revoke_unreachable") from None
    if response.status_code != HTTP_OK:
        raise KaggleSignInError("revoke_unreachable")


def token_grant_from(answer: dict) -> TokenGrant:
    """Read Kaggle's token answer, which spells each field both snake_case and camelCase."""
    access_token = answer.get("access_token") or answer.get("accessToken")
    if not isinstance(access_token, str) or not access_token:
        raise KaggleSignInError("refused")
    return TokenGrant(
        access_token=access_token,
        refresh_token=answer.get("refresh_token") or answer.get("refreshToken") or None,
        expires_in_seconds=int(answer.get("expires_in") or answer.get("expiresIn") or 0),
        username=answer.get("username") or None,
    )


async def _post_or_refuse(http: httpx.AsyncClient, url: str, **body: object) -> dict:
    # Kaggle's error bodies are never passed on: a fixed reason is all the caller gets.
    try:
        response = await http.post(url, **body)
    except httpx.HTTPError:
        raise KaggleSignInError("refused") from None
    if response.status_code != HTTP_OK:
        raise KaggleSignInError("refused")
    return _json_or_empty(response)


def _json_or_empty(response: httpx.Response) -> dict:
    try:
        answer = response.json()
    except ValueError:
        return {}
    return answer if isinstance(answer, dict) else {}


def _is_invalid_grant(response: httpx.Response) -> bool:
    return _json_or_empty(response).get("error") == INVALID_GRANT
