"""Run / Skip, Download / Skip and Delete / Keep prompts go through the Asker port."""

import asyncio
import json

import pytest

from researchchat.tools import dataset_delete, dataset_download, notebook_run
from researchchat.workspace import ErrorCode, store
from researchchat.workspace.datasets.sources import DatasetPlan, PlannedFile
from researchchat.workspace.service import NotebookService
from tests.chat.fakes import FakeAsker, in_chat
from tests.conftest import FakeDatasetService
from tests.datasets.test_dataset_tools import STARTED

RISKY_CODE = "!ls"  # a shell command: the risk check always asks first

# ---- Prompts through the Asker port · unit
# Baseline: Given notebook_run with risky code and a FakeAsker · When the tool runs


@pytest.fixture
def notebook(tmp_path, fake_kernels):
    root = tmp_path / "workspaces"
    project_id = store.create_project("P", root).id

    async def notify(_project_id, _props):
        pass

    return NotebookService(fake_kernels, root=root, notify=notify), project_id


def run_risky_code(notebook, answer: str | None) -> tuple[FakeAsker, str]:
    svc, project_id = notebook
    asker = FakeAsker(answer=answer)
    with in_chat(asker=asker):
        _shown, result = asyncio.run(notebook_run.run({"code": RISKY_CODE}, svc=svc, project_id=project_id))
    return asker, result


def test_risky_code_runs_after_run_is_chosen(notebook, fake_kernels):
    # Given the asker answers "run"
    # When notebook_run gets risky code
    # Then the user was asked with the code and the reasons, and the code ran
    # Demonstrates: approval works through the port
    asker, _result = run_risky_code(notebook, "run")

    [(question, choices)] = asker.asked
    assert RISKY_CODE in question and "runs a shell command" in question
    assert [(choice.id, choice.label) for choice in choices] == [("run", "Run"), ("skip", "Skip")]
    assert fake_kernels.executed == [RISKY_CODE]


def test_risky_code_is_skipped_on_skip(notebook, fake_kernels):
    # Given the asker answers "skip"
    # When notebook_run gets risky code
    # Then nothing ran and the model is told the user skipped it
    # Demonstrates: Skip is respected
    _asker, result = run_risky_code(notebook, "skip")

    assert result == notebook_run.DECLINED
    assert fake_kernels.executed == []


def test_risky_code_is_skipped_when_nobody_answers(notebook, fake_kernels):
    # Given the asker answers None, as when the prompt times out
    # When notebook_run gets risky code
    # Then nothing ran and the model gets the same skipped result
    # Demonstrates: no answer counts as Skip
    _asker, result = run_risky_code(notebook, None)

    assert result == notebook_run.DECLINED
    assert fake_kernels.executed == []


class AskingDatasetService(FakeDatasetService):
    """Asks before a big download, as the real service does above its ask size."""

    def __init__(self, plan: DatasetPlan, download_bytes: int):
        super().__init__()
        self.plan = plan
        self.download_bytes = download_bytes
        self.started = STARTED
        self.queued = False

    async def request(self, project_id, session_id, ref, files=None, update=False, *, approve, pasted_links=frozenset()):
        if await approve(self.plan, self.download_bytes):
            self.queued = True
        return await super().request(project_id, session_id, ref, files, update, approve=approve, pasted_links=pasted_links)


def test_big_download_asks_and_downloads_on_download():
    # Given a download above the ask size and the asker answers "download"
    # When dataset_download runs
    # Then the user saw the name, file count, size and licence, and the download was queued
    # Demonstrates: other prompts use the same port
    plan = DatasetPlan(
        source="hf", source_id="org/name", name="Hanoi PM2.5", revision="abc", url="https://huggingface.co/datasets/org/name",
        license="cc-by-4.0", files=[PlannedFile("a.csv", 150_000_000, None, "https://x/a.csv"), PlannedFile("b.csv", 150_000_000, None, "https://x/b.csv")],
    )
    svc = AskingDatasetService(plan, download_bytes=300_000_000)
    asker = FakeAsker(answer="download")

    with in_chat(asker=asker):
        asyncio.run(dataset_download.run({"ref": "hf:org/name"}, svc=svc, project_id="p1", session_id="s1", pasted_links=frozenset()))

    [(question, choices)] = asker.asked
    assert "Hanoi PM2.5" in question and "2 files" in question and "cc-by-4.0" in question
    assert [choice.id for choice in choices] == ["download", "skip"]
    assert svc.queued


class FakeDeleter:
    def __init__(self):
        self.deleted: list[str] = []

    def describe(self, project_id, dataset_id):
        return {"dataset_id": dataset_id, "name": "Hanoi PM2.5", "size_bytes": 2048, "shared_with": 0}

    async def delete(self, project_id, dataset_id):
        self.deleted.append(dataset_id)
        return {"deleted": True, "freed_bytes": 2048, "still_used_by": 0}


def test_dataset_delete_keeps_data_on_keep():
    # Given the asker answers "keep"
    # When dataset_delete runs
    # Then nothing was deleted and the model is told the user kept it
    # Demonstrates: Keep is respected
    svc = FakeDeleter()
    asker = FakeAsker(answer="keep")

    with in_chat(asker=asker):
        _shown, result = asyncio.run(dataset_delete.run({"dataset_id": "hf-org--name"}, svc=svc, project_id="p1"))

    assert json.loads(result)["error"] == ErrorCode.DECLINED
    assert [choice.id for _question, choices in asker.asked for choice in choices] == ["delete", "keep"]
    assert svc.deleted == []
