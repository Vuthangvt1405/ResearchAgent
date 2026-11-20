"""The one-shot loopback listener that catches Kaggle's redirect after the user approves."""

import asyncio
import urllib.parse

import httpx

from researchchat.workspace.kaggle.callback import (
    CANCELLED_PAGE,
    CONNECTED_PAGE,
    CallbackListener,
)

STATE = "state-abc"


def run(coro):
    return asyncio.run(coro)


def loopback_url(redirect_uri: str, path_and_query: str) -> str:
    port = urllib.parse.urlsplit(redirect_uri).port
    return f"http://127.0.0.1:{port}{path_and_query}"


async def get(redirect_uri: str, path_and_query: str) -> httpx.Response:
    async with httpx.AsyncClient() as http:
        return await http.get(loopback_url(redirect_uri, path_and_query))


# Baseline: Given a listener on 127.0.0.1 port 0 expecting a known state · When the test requests the callback with a code and that state


def test_valid_callback_returns_code() -> None:
    # Changed: — · Then: the code is returned, the tab says Connected, and the listener closes · Demonstrates: the browser hand-off works
    async def scenario():
        listener = CallbackListener(STATE, timeout_seconds=5)
        redirect = await listener.start()
        waiting = asyncio.create_task(listener.wait())
        reply = await get(redirect, f"/callback?code=C-1&state={STATE}")
        result = await waiting
        try:
            await get(redirect, f"/callback?code=C-2&state={STATE}")
            still_open = True
        except httpx.ConnectError:
            still_open = False
        return redirect, reply, result, still_open

    redirect, reply, result, still_open = run(scenario())
    assert redirect.startswith("http://localhost:") and redirect.endswith("/callback")
    assert (reply.status_code, reply.text) == (200, CONNECTED_PAGE)
    assert (result.outcome, result.code) == ("code", "C-1")
    assert not still_open


def test_error_callback_is_cancelled() -> None:
    # Changed: error=access_denied with our state · Then: cancelled, the tab says Sign-in cancelled · Demonstrates: Cancel on Kaggle is understood
    async def scenario():
        listener = CallbackListener(STATE, timeout_seconds=5)
        redirect = await listener.start()
        waiting = asyncio.create_task(listener.wait())
        reply = await get(redirect, f"/callback?error=access_denied&state={STATE}")
        return reply, await waiting

    reply, result = run(scenario())
    assert (reply.status_code, reply.text) == (200, CANCELLED_PAGE)
    assert (result.outcome, result.code) == ("cancelled", None)


def test_wrong_state_is_ignored() -> None:
    # Changed: a wrong state first, then the right one · Then: 404 and still waiting, then the code · Demonstrates: forged callbacks don't count
    async def scenario():
        listener = CallbackListener(STATE, timeout_seconds=5)
        redirect = await listener.start()
        waiting = asyncio.create_task(listener.wait())
        forged = await get(redirect, "/callback?code=EVIL&state=other")
        done_after_forged = waiting.done()
        await get(redirect, f"/callback?code=GOOD&state={STATE}")
        return forged, done_after_forged, await waiting

    forged, done_after_forged, result = run(scenario())
    assert forged.status_code == 404
    assert not done_after_forged
    assert result.code == "GOOD"


def test_stray_paths_are_ignored() -> None:
    # Changed: favicon and root requests first · Then: 404s and still waiting · Demonstrates: browser noise doesn't end the sign-in
    async def scenario():
        listener = CallbackListener(STATE, timeout_seconds=5)
        redirect = await listener.start()
        waiting = asyncio.create_task(listener.wait())
        strays = [await get(redirect, path) for path in ("/favicon.ico", "/", f"/other?state={STATE}&code=X")]
        done_after_strays = waiting.done()
        await get(redirect, f"/callback?code=GOOD&state={STATE}")
        return strays, done_after_strays, await waiting

    strays, done_after_strays, result = run(scenario())
    assert [r.status_code for r in strays] == [404, 404, 404]
    assert not done_after_strays
    assert result.code == "GOOD"


def test_times_out() -> None:
    # Changed: no request, 0.2 s timeout · Then: timed_out and the port is closed · Demonstrates: a forgotten tab doesn't hold a port
    async def scenario():
        listener = CallbackListener(STATE, timeout_seconds=0.2)
        redirect = await listener.start()
        result = await listener.wait()
        try:
            await get(redirect, f"/callback?code=LATE&state={STATE}")
            port_open = True
        except httpx.ConnectError:
            port_open = False
        return result, port_open

    result, port_open = run(scenario())
    assert result.outcome == "timed_out"
    assert not port_open


def test_listens_on_loopback_only() -> None:
    # Changed: inspect the socket · Then: bound to 127.0.0.1 · Demonstrates: other machines can't reach it
    async def scenario():
        listener = CallbackListener(STATE, timeout_seconds=5)
        await listener.start()
        hosts = [s.getsockname()[0] for s in listener._server.sockets]
        await listener.close()
        return hosts

    assert run(scenario()) == ["127.0.0.1"]
