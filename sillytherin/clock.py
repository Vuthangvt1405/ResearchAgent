"""The app's one timestamp format: ISO 8601 UTC to the second, with a Z suffix (2026-11-16T10:00:00Z)."""

from datetime import UTC, datetime

UTC_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utc_now() -> str:
    return datetime.now(UTC).strftime(UTC_TIMESTAMP_FORMAT)
