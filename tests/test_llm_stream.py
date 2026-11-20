"""The model stream's connection is closed however a round ends."""

import asyncio
from types import SimpleNamespace
from typing import Self

import pytest

from researchchat import llm
from researchchat.progress import Progress
from tests.chat.fakes import FakeProgressView


class FakeStream:
    """Stands in for openai's AsyncStream: yields chunks, then optionally fails mid-stream."""

    def __init__(self, chunks: list, fail_after: int | None = None):
        self.chunks = chunks
        self.fail_after = fail_after
        self.closed = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        self.closed = True

    def __aiter__(self):
        return self._chunks()

    async def _chunks(self):
        for index, chunk in enumerate(self.chunks):
            if self.fail_after is not None and index == self.fail_after:
                raise asyncio.CancelledError  # what pressing Stop does to the running message
            yield chunk


def text_chunk(text: str) -> SimpleNamespace:
    delta = SimpleNamespace(content=text, reasoning=None, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


class FakeReply:
    def __init__(self) -> None:
        self.tokens: list[str] = []

    async def stream(self, text: str) -> None:
        self.tokens.append(text)

    async def finish(self, text: str) -> None:
        pass


def use_stream(monkeypatch, stream: FakeStream) -> None:
    async def create(**_request: object) -> FakeStream:
        return stream

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm, "client", fake_client)


# Baseline: Given a model stream of two text chunks · When stream_round reads it


def test_stream_closed_after_a_full_round(monkeypatch) -> None:
    # Then: the text is returned and the connection is closed · Demonstrates: a normal round leaves nothing open
    stream = FakeStream([text_chunk("Hel"), text_chunk("lo")])
    use_stream(monkeypatch, stream)
    reply = FakeReply()
    text, calls = asyncio.run(llm.stream_round([], reply, {}, Progress(FakeProgressView())))
    assert (text, calls, reply.tokens) == ("Hello", [], ["Hel", "lo"])
    assert stream.closed


def test_stream_closed_when_the_round_is_stopped(monkeypatch) -> None:
    # Changed: the round is cancelled after the first chunk · Then: the connection is still closed in this task · Demonstrates: Stop doesn't leave the connection to the garbage collector
    stream = FakeStream([text_chunk("Hel"), text_chunk("lo")], fail_after=1)
    use_stream(monkeypatch, stream)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(llm.stream_round([], FakeReply(), {}, Progress(FakeProgressView())))
    assert stream.closed
