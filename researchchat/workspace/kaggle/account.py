"""The user's Kaggle account: connect, disconnect, and short-lived access tokens for downloads.

One account for the whole app, so every project uses the same sign-in.
"""

import asyncio
import contextlib
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol

import httpx

from researchchat.clock import utc_now
from researchchat.workspace import ErrorCode, WorkspaceError
from researchchat.workspace.kaggle import oauth
from researchchat.workspace.kaggle.callback import CallbackListener, CallbackResult
from researchchat.workspace.kaggle.token_file import SavedSignIn, TokenFile

CANCELLED_NOTICE = "Kaggle sign-in was cancelled."
TIMED_OUT_NOTICE = "Kaggle sign-in timed out. Try again."
REFUSED_NOTICE = "Couldn't connect to Kaggle. Try again."
SIGNED_OUT_NOTICE = "Kaggle signed you out. Turn on to connect again."
REVOKE_UNREACHABLE_NOTICE = (
    "Disconnected here. Kaggle couldn't be reached to cancel the sign-in; "
    "you can remove SillyTherin under kaggle.com → Settings."
)
NOTICE_FOR_FAILURE: dict[oauth.SignInFailure, str] = {
    "cancelled": CANCELLED_NOTICE,
    "timed_out": TIMED_OUT_NOTICE,
    "refused": REFUSED_NOTICE,
    "signed_out": SIGNED_OUT_NOTICE,
    "revoke_unreachable": REVOKE_UNREACHABLE_NOTICE,
}
STATE_BYTES = 32
EXPIRY_MARGIN_SECONDS = 300  # refresh a little early so a download never starts with a token about to expire

AccountState = Literal["disconnected", "connecting", "connected"]


@dataclass(frozen=True)
class KaggleAccountStatus:
    """What Settings shows; never holds a token."""

    state: AccountState
    username: str | None = None
    notice: str | None = None


class KaggleAccount(Protocol):
    """What dataset downloads need from the account."""

    async def access_token(self) -> str | None:
        """A Bearer token for api.kaggle.com, or None when no account is connected."""
        ...


AccountChanged = Callable[[KaggleAccountStatus], Awaitable[None]]
HttpFactory = Callable[[], httpx.AsyncClient]
ListenerFactory = Callable[[str, float], CallbackListener]  # (expected state, timeout seconds) -> listener
Now = Callable[[], float]  # monotonic seconds, to know when the access token runs out


@dataclass
class PendingSignIn:
    listener: CallbackListener
    finished: asyncio.Task | None = None


@dataclass(frozen=True)
class CachedAccessToken:
    token: str = field(repr=False)
    refresh_at: float  # monotonic seconds


class KaggleAccountService:
    """Coordinates the sign-in steps; callers get a status, never a token, except through access_token()."""

    def __init__(
        self,
        token_file: TokenFile,
        http_factory: HttpFactory,
        listener_factory: ListenerFactory,
        signin_timeout_seconds: float,
        now: Now,
        on_change: AccountChanged,
    ):
        self.token_file = token_file
        self.http_factory = http_factory
        self.listener_factory = listener_factory
        self.signin_timeout_seconds = signin_timeout_seconds
        self.now = now
        self.on_change = on_change
        self._pending: PendingSignIn | None = None
        self._cached: CachedAccessToken | None = None
        self._notice: str | None = None
        self._refresh_lock = asyncio.Lock()

    def status(self) -> KaggleAccountStatus:
        if self._pending is not None:
            return KaggleAccountStatus("connecting")
        saved = self.token_file.load()
        if saved is not None:
            return KaggleAccountStatus("connected", username=saved.username)
        return KaggleAccountStatus("disconnected", notice=self._notice)

    async def start_connect(self) -> str | None:
        """Start a sign-in and return Kaggle's approval page URL; None when already connected."""
        if self.token_file.load() is not None:
            return None
        await self.cancel_connect()
        self._notice = None
        state = secrets.token_urlsafe(STATE_BYTES)
        listener = self.listener_factory(state, self.signin_timeout_seconds)
        redirect_uri = await listener.start()
        try:
            async with self.http_factory() as http:
                client = await oauth.register_client(http, redirect_uri)
        except oauth.KaggleSignInError:
            await listener.close()
            raise WorkspaceError(ErrorCode.KAGGLE_SIGNIN, REFUSED_NOTICE) from None
        pkce = oauth.make_pkce_pair()
        pending = PendingSignIn(listener)
        pending.finished = asyncio.create_task(self._finish_sign_in(pending, client, pkce))
        self._pending = pending
        return oauth.build_authorize_url(client, state, pkce)

    async def wait_for_sign_in(self) -> KaggleAccountStatus:
        """Wait until a started sign-in ends, then return the new status."""
        pending = self._pending
        if pending is not None and pending.finished is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.shield(pending.finished)
        return self.status()

    async def cancel_connect(self) -> None:
        pending = self._pending
        if pending is None:
            return
        await pending.listener.close()
        if pending.finished is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await pending.finished

    async def disconnect(self) -> None:
        if self._pending is not None:
            await self.cancel_connect()
            return
        saved = self.token_file.load()
        self._notice = None
        if saved is not None:
            self._notice = await self._revoke_on_kaggle(saved)
        self.token_file.delete()
        self._cached = None
        await self.on_change(self.status())

    async def access_token(self) -> str | None:
        saved = self.token_file.load()
        if saved is None:
            self._cached = None
            return None
        if self._cached_is_fresh():
            return self._cached.token
        async with self._refresh_lock:
            if self._cached_is_fresh():
                return self._cached.token
            return await self._refresh(saved)

    # ---- steps ----

    async def _finish_sign_in(self, pending: PendingSignIn, client: oauth.OAuthClient, pkce: oauth.PkcePair) -> None:
        result = await pending.listener.wait()
        try:
            if self._pending is pending:
                self._notice = await self._save_sign_in(result, client, pkce)
        finally:
            if self._pending is pending:
                self._pending = None
                await self.on_change(self.status())

    async def _save_sign_in(self, result: CallbackResult, client: oauth.OAuthClient, pkce: oauth.PkcePair) -> str | None:
        """Exchange the code and save the sign-in; the notice to show when it didn't happen."""
        if result.outcome != "code" or result.code is None:
            return NOTICE_FOR_FAILURE["timed_out" if result.outcome == "timed_out" else "cancelled"]
        try:
            async with self.http_factory() as http:
                grant = await oauth.exchange_code(http, client, result.code, pkce)
        except oauth.KaggleSignInError as failure:
            return NOTICE_FOR_FAILURE[failure.reason]
        if not grant.refresh_token:
            return REFUSED_NOTICE
        self.token_file.save(
            SavedSignIn(
                client_id=client.client_id,
                refresh_token=grant.refresh_token,
                username=grant.username or "your Kaggle account",
                connected_at=utc_now(),
            )
        )
        self._remember(grant)
        return None

    async def _refresh(self, saved: SavedSignIn) -> str | None:
        try:
            async with self.http_factory() as http:
                grant = await oauth.refresh_access_token(http, saved.client_id, saved.refresh_token)
        except oauth.KaggleSignInError as failure:
            if failure.reason == "signed_out":
                await self._forget_signed_out_account()
            return None  # a network problem keeps the sign-in; the next download tries again
        if grant.refresh_token and grant.refresh_token != saved.refresh_token:
            self.token_file.save(SavedSignIn(saved.client_id, grant.refresh_token, saved.username, saved.connected_at))
        self._remember(grant)
        return grant.access_token

    async def _revoke_on_kaggle(self, saved: SavedSignIn) -> str | None:
        """Cancel the sign-in on Kaggle; the notice to show when Kaggle couldn't be reached."""
        access = self._cached.token if self._cached_is_fresh() else await self._refresh(saved)
        if access is None:
            return None if self.token_file.load() is None else REVOKE_UNREACHABLE_NOTICE
        try:
            async with self.http_factory() as http:
                await oauth.revoke_refresh_token(http, access, saved.refresh_token)
        except oauth.KaggleSignInError:
            return REVOKE_UNREACHABLE_NOTICE
        return None

    async def _forget_signed_out_account(self) -> None:
        self.token_file.delete()
        self._cached = None
        self._notice = SIGNED_OUT_NOTICE
        await self.on_change(self.status())

    def _remember(self, grant: oauth.TokenGrant) -> None:
        self._cached = CachedAccessToken(grant.access_token, self.now() + grant.expires_in_seconds - EXPIRY_MARGIN_SECONDS)

    def _cached_is_fresh(self) -> bool:
        return self._cached is not None and self.now() < self._cached.refresh_at
