"""Live checks: the real assistant follows the reuse rules.

Talks to the configured model through OpenRouter with fake tools that record
calls. Opt-in only: `pytest -m live` (pytest.ini deselects them by default);
skipped without OPENROUTER_API_KEY. Costs a few cents per run.
"""

import asyncio
import json
import os
import re

import pytest

import researchchat.config  # noqa: F401 — loads .env, so the key there counts
from tests.conftest import FakeDatasetService
from tests.test_dataset_reuse import (
    IRIS_COLUMNS,
    SEARCH_RESULTS,
    created_record,
    record,
)

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("OPENROUTER_API_KEY"), reason="needs OPENROUTER_API_KEY"),
]

MAX_ROUNDS = 8
IRIS_PATH = "/work/datasets/hf-scikit-learn--iris"
FIRST_ROWS = (
    "[cell 1] out:    sepal_length  sepal_width  petal_length  petal_width species\n"
    "0           5.1          3.5           1.4          0.2  setosa\n"
    "1           4.9          3.0           1.4          0.2  setosa"
)
WRITES_A_FILE = re.compile(r"\.to_(csv|parquet|excel|json|feather)\(|open\([^)]*['\"][wa]")


class Chat:
    """One scripted conversation: the real model, fake tools, every call recorded."""

    def __init__(self, records: list[dict]):
        from researchchat.tools.dataset_describe import ChatLooks

        self.svc = FakeDatasetService()
        self.svc.records = records
        self.calls: list[tuple[str, dict]] = []
        self.retry_questions: list[str] = []  # names the "Download again?" question was shown for
        self.looked, self.notebook = ChatLooks(), FirstRows()
        self.svc.started = {"dataset_id": "hf-other--iris", "status": "queued", "already_downloaded": False,
                            "position_in_queue": 1, "size_bytes": 10, "download_bytes": 10,
                            "path": "/work/datasets/hf-other--iris", "files": [], "license": None, "url": None,
                            "note": "Downloading in the background. Don't read the files until then.", "from_pool": False}

    async def ask(self, user_text: str) -> str:
        from openai import AsyncOpenAI

        from researchchat.config import (
            MODEL,
            OPENROUTER_API_KEY,
            OPENROUTER_URL,
            SYSTEM_PROMPT,
        )
        from researchchat.tools import NOTEBOOK_TOOLS, TOOLS

        # A client per chat: the app's shared one is tied to the event loop of the first test
        client = AsyncOpenAI(base_url=OPENROUTER_URL, api_key=OPENROUTER_API_KEY)

        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_text}]
        for _ in range(MAX_ROUNDS):
            response = await client.chat.completions.create(
                model=MODEL, messages=messages, tools=TOOLS + NOTEBOOK_TOOLS, temperature=0,
            )
            message = response.choices[0].message
            if not message.tool_calls:
                return message.content or ""
            messages.append({
                "role": "assistant", "content": message.content,
                "tool_calls": [call.model_dump() for call in message.tool_calls],
            })
            for call in message.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                self.calls.append((call.function.name, args))
                messages.append({"role": "tool", "tool_call_id": call.id, "content": await self.tool(call.function.name, args)})
        return ""

    async def tool(self, name: str, args: dict) -> str:
        from researchchat.tools import dataset_list

        if name == "dataset_list":
            return (await dataset_list.run({}, svc=self.svc, project_id="p1"))[1]
        if name == "dataset_search":  # the real tool (marks, reminders) with canned catalog answers
            from researchchat.tools import dataset_search

            async def canned(query, task="", language=""):
                return [dict(r) for r in SEARCH_RESULTS], []

            real_search, dataset_search.search = dataset_search.search, canned
            try:
                return (await dataset_search.run(args, svc=self.svc, project_id="p1"))[1]
            finally:
                dataset_search.search = real_search
        if name == "dataset_download":  # the real tool: a broken copy gets the "Download again?" question, answered No
            from researchchat.tools import dataset_download

            async def say_no(name, reason):
                self.retry_questions.append(name)
                return False

            try:
                return (await dataset_download.run(
                    args, svc=self.svc, project_id="p1", session_id="s1", approve=yes, pasted_links=frozenset(),
                    confirm_retry=say_no, looked=self.looked,
                ))[1]
            except ValueError as e:
                return f"Tool failed: {e}"
        if name == "notebook_run":  # the real tool, so looks at undescribed data are recorded
            from researchchat.tools import notebook_run

            return (await notebook_run.run(
                args, svc=self.notebook, project_id="p1", approve=yes_to_code, datasets=self.svc, session_id="s1",
                looked=self.looked,
            ))[1]
        if name == "dataset_describe":
            if args.get("description"):
                return json.dumps({"saved": args.get("dataset_id"), "description": args["description"]})
            return json.dumps({"allowed": True, "next": "Look at its first rows with notebook_run, then call again with a description."})
        return "Not available in this test."

    def names(self) -> list[str]:
        return [name for name, _args in self.calls]

    def file_writes(self) -> list[str]:
        return [a.get("code", "") for n, a in self.calls if n == "notebook_run" and WRITES_A_FILE.search(a.get("code", ""))]

    def fetched(self) -> bool:
        """True when a download really reached the service (not stopped by a question)."""
        return any(call[0] == "request" for call in self.svc.calls)

    def assert_nothing_new(self) -> None:
        assert not self.fetched(), self.calls
        assert self.file_writes() == [], self.calls


def run(coro):
    return asyncio.run(coro)


async def yes(plan, size):
    return True


async def yes_to_code(code, reasons):
    return True


class FirstRows:
    """Stands in for NotebookService.run_for_model: every run prints the iris head."""

    async def run_for_model(self, project_id, code):
        return FIRST_ROWS


# ---- The real assistant follows the rules · live, opt-in `@pytest.mark.live`
# Baseline: scripted chat with the configured model, fake tools that record calls, project with iris ready (with description) · run with `pytest -m live`; skipped without `OPENROUTER_API_KEY`


def test_live_ready_dataset_is_reused():
    # Positive · Changed: "create an iris dataset"
    # Then: `dataset_list` before any `dataset_search`; no download / file write; path in reply
    # Demonstrates: a matching dataset is reused, and it looks first unprompted
    chat = Chat([record()])
    reply = run(chat.ask("create an iris dataset"))
    names = chat.names()
    assert "dataset_list" in names
    if "dataset_search" in names:
        assert names.index("dataset_list") < names.index("dataset_search")
    chat.assert_nothing_new()
    assert IRIS_PATH in reply


def test_live_created_file_is_reused():
    # Positive · Changed: only created `Iris.csv`
    # Then: `/work/Iris.csv`; no new file
    # Demonstrates: a created file is reused too
    chat = Chat([created_record("Iris.csv")])
    reply = run(chat.ask("get me the iris data"))
    chat.assert_nothing_new()
    assert "/work/Iris.csv" in reply


def test_live_request_in_other_words_finds_it():
    # Positive · Changed: "get me the flower petal measurements"
    # Then: iris path; no download
    # Demonstrates: a request in other words still finds the data
    chat = Chat([record()])
    reply = run(chat.ask("get me the flower petal measurements"))
    chat.assert_nothing_new()
    assert IRIS_PATH in reply


def test_live_neutral_file_found_by_columns():
    # Positive · Changed: `data.csv` with iris columns
    # Then: `/work/data.csv`
    # Demonstrates: columns work end to end
    chat = Chat([created_record("data.csv", columns=IRIS_COLUMNS)])
    reply = run(chat.ask("I need the iris flower data for a quick analysis"))
    chat.assert_nothing_new()
    assert "/work/data.csv" in reply


def test_live_assistant_file_is_looked_at_and_described():
    # Positive · Changed: assistant `data.xls`, nothing known
    # Then: `notebook_run` reading first rows, then `dataset_describe` with text, no ask
    # Demonstrates: data that says nothing about itself is looked at and described
    chat = Chat([created_record("data.xls", columns=[], describe="write")])
    run(chat.ask("I need the iris flower data for a quick analysis"))
    names = chat.names()
    assert "notebook_run" in names and "dataset_describe" in names, chat.calls
    assert names.index("notebook_run") < names.index("dataset_describe")
    assert any(n == "dataset_describe" and a.get("description") for n, a in chat.calls), chat.calls
    assert chat.file_writes() == []


def test_live_no_match_searches_as_today():
    # Positive · Changed: empty project
    # Then: `dataset_search` called
    # Demonstrates: with no match, it searches as before
    chat = Chat([])
    run(chat.ask("find me an iris dataset"))
    assert "dataset_search" in chat.names(), chat.calls


def test_live_failed_match_offers_download():
    # Negative · Changed: iris `failed`; the fake retry question answers No
    # Then: no file write; either it asks in words, or it calls `dataset_download` and the app asks
    # Demonstrates: a broken copy is not downloaded again without a yes
    chat = Chat([record(status="failed", error="Download failed: connection lost", ref="hf:scikit-learn/iris")])
    reply = run(chat.ask("get me the iris data"))
    chat.assert_nothing_new()  # a download call is fine: the app asked "Download again?" and the fake user said No
    if "dataset_download" in chat.names():
        assert chat.retry_questions == ["hf-scikit-learn--iris"], chat.calls
    else:
        assert "download" in reply.lower()


def test_live_explicit_new_copy_is_made():
    # Positive · Changed: "make a new iris file anyway"
    # Then: `notebook_run` or `dataset_download`
    # Demonstrates: a new copy is made when the user asks for one
    chat = Chat([record()])
    run(chat.ask("I know I already have iris. Make a new iris file anyway, saved as /work/iris_copy.csv."))
    assert "notebook_run" in chat.names() or "dataset_download" in chat.names(), chat.calls


def test_live_two_matches_asks_which():
    # Negative · Changed: download + created iris
    # Then: names both; nothing created
    # Demonstrates: with two matches, it asks which
    chat = Chat([record(), created_record("Iris.csv")])
    reply = run(chat.ask("get me the iris data"))
    chat.assert_nothing_new()
    assert "hf-scikit-learn--iris" in reply and "Iris.csv" in reply


def test_live_uploaded_file_is_read_without_asking():
    # Negative · Changed: a file the user put in, `upload.xls`, nothing known
    # Then: the assistant opens it with notebook_run (no question exists) before any download, and describes it
    # Demonstrates: every file in the project is already allowed
    chat = Chat([created_record("upload.xls", columns=[], describe="write")])
    run(chat.ask("Is there any iris flower data in my project I can use?"))
    names = chat.names()
    opened = [i for i, (n, a) in enumerate(chat.calls) if n == "notebook_run" and "upload.xls" in a.get("code", "").lower()]
    assert opened, chat.calls
    if "dataset_download" in names:
        assert opened[0] < names.index("dataset_download"), chat.calls
