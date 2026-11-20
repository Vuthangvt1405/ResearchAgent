"""Which pages and host names may talk to the app.

The app runs code and has no login, so a request is only served when it comes from the
app's own page on this PC: any other website open in the browser is refused.
"""

LOOPBACK_NAMES = ("127.0.0.1", "localhost", "[::1]")


def allowed_origins(port: int) -> frozenset[str]:
    """The app's own page addresses, e.g. `http://127.0.0.1:8000`."""
    return frozenset(f"http://{name}:{port}" for name in LOOPBACK_NAMES)


def allowed_hosts(port: int) -> frozenset[str]:
    """The Host header values the app answers to; anything else may be DNS rebinding."""
    return frozenset(f"{name}:{port}" for name in LOOPBACK_NAMES)


def is_allowed_origin(origin: str | None, port: int) -> bool:
    """Exactly one of the app's own page addresses; a missing or "null" origin is refused."""
    return origin is not None and origin in allowed_origins(port)


def is_allowed_host(host: str | None, port: int) -> bool:
    return host is not None and host in allowed_hosts(port)
