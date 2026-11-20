"""A download's connection is opened, read and closed in one task.

httpcore refuses to close a connection from another task ("Attempted to exit cancel
scope in a different task"), which asyncio.wait_for caused on Python 3.11 by running
each step in a task of its own.
"""

import asyncio

import httpx
import pytest

from researchchat.workspace.datasets import links
from researchchat.workspace.datasets import sources as src
from tests.conftest import catalog_client, fake_lookup

BODY_CHUNKS = [b"a,b\n", b"1,2\n", b"3,4\n"]


@pytest.fixture(autouse=True)
def no_dns(monkeypatch):
    monkeypatch.setattr(src, "lookup_host", fake_lookup)


class TaskRecordingBody(httpx.AsyncByteStream):
    """A response body that notes which task reads each chunk and which task closes it."""

    def __init__(self, tasks: list[str]):
        self.tasks = tasks

    async def __aiter__(self):
        for chunk in BODY_CHUNKS:
            self.tasks.append(f"read:{id(asyncio.current_task())}")
            yield chunk

    async def aclose(self) -> None:
        self.tasks.append(f"close:{id(asyncio.current_task())}")


def recording_handler(tasks: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=TaskRecordingBody(tasks))

    return handler


async def nothing(_count: int) -> None:
    pass


def tasks_used(tasks: list[str]) -> set[str]:
    return {entry.split(":", 1)[1] for entry in tasks}


# Baseline: Given a catalog file of 12 bytes in 3 chunks · When it is downloaded


def test_catalog_download_reads_and_closes_in_one_task(tmp_path) -> None:
    # Then: every chunk read and the close happen in the downloading task · Demonstrates: no cross-task close warning
    tasks: list[str] = []
    planned = src.PlannedFile("iris.csv", 12, None, "https://huggingface.co/datasets/x/y/resolve/abc/iris.csv")

    async def download() -> str:
        async with catalog_client(recording_handler(tasks)) as client:
            await src.stream_file(planned, tmp_path / "iris.csv", client=client, on_bytes=nothing, stall_timeout=5)
        return str(id(asyncio.current_task()))

    downloading_task = asyncio.run(download())
    assert (tmp_path / "iris.csv").read_bytes() == b"".join(BODY_CHUNKS)
    assert [entry.split(":")[0] for entry in tasks] == ["read", "read", "read", "close"]
    assert tasks_used(tasks) == {downloading_task}


def test_pasted_link_download_reads_and_closes_in_one_task(tmp_path) -> None:
    # Changed: a pasted file link instead of a catalog file · Then: the same single task · Demonstrates: both download paths are fixed
    tasks: list[str] = []
    planned = src.PlannedFile("iris.csv", 12, None, "https://example.org/data/iris.csv")

    async def download() -> str:
        async with catalog_client(recording_handler(tasks)) as client:
            await links.stream_link_file(planned, tmp_path / "iris.csv", client=client, on_bytes=nothing, stall_timeout=5)
        return str(id(asyncio.current_task()))

    downloading_task = asyncio.run(download())
    assert (tmp_path / "iris.csv").read_bytes() == b"".join(BODY_CHUNKS)
    assert tasks_used(tasks) == {downloading_task}


def test_stalled_body_still_times_out(tmp_path) -> None:
    # Changed: the second chunk never arrives · Then: DOWNLOAD_FAILED "stalled on iris.csv" · Demonstrates: the stall timeout still works without wait_for
    class StallingBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield BODY_CHUNKS[0]
            await asyncio.sleep(10)
            yield BODY_CHUNKS[1]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=StallingBody())

    planned = src.PlannedFile("iris.csv", 12, None, "https://huggingface.co/datasets/x/y/resolve/abc/iris.csv")

    async def download() -> None:
        async with catalog_client(handler) as client:
            await src.stream_file(planned, tmp_path / "iris.csv", client=client, on_bytes=nothing, stall_timeout=0.2)

    with pytest.raises(src.WorkspaceError) as raised:
        asyncio.run(download())
    assert raised.value.message == "stalled on iris.csv"
