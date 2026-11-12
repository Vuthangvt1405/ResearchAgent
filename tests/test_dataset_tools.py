"""Tests for the dataset_download / dataset_list / dataset_delete tools and the
search ref (NB-3 plan §7: G8, S❌3). Tools get a fake dataset service."""

import asyncio
import json

import pytest

from researchchat.tools import chosen_tools, dataset_download, dataset_list
from researchchat.tools import dataset_search as search
from researchchat.workspace import ErrorCode, WorkspaceError
from researchchat.workspace import store
from researchchat.workspace.dataset_service import DatasetService, DatasetsSettings
from researchchat.workspace.dataset_sources import DatasetPlan, PlannedFile
from tests.conftest import FakeDatasetService, FakeFreeDisk

STARTED = {
    "dataset_id": "hf-org--name",
    "status": "downloading",
    "already_downloaded": False,
    "position_in_queue": 0,
    "size_bytes": 1000,
    "download_bytes": 1000,
    "path": "/work/datasets/hf-org--name",
    "files": [{"path": "/work/datasets/hf-org--name/a.csv", "size": 1000}],
    "license": "mit",
    "url": "https://huggingface.co/datasets/org/name",
    "note": "Downloading in the background. The user can keep chatting; you'll be told when it's ready. Don't read the files until then.",
}


def view(id, status, done=None, position=None, size=1000):
    return {
        "dataset_id": id, "name": id, "status": status, "done_bytes": done, "position_in_queue": position,
        "size_bytes": size, "license": "mit", "url": None, "path": f"/work/datasets/{id}", "files": [],
        "file_count": 1, "missing_files": [], "downloaded_at": None, "error": None,
    }


async def never(plan, size):
    raise AssertionError("asked")


def run(coro):
    return asyncio.run(coro)


# ---- Group 8 — Model tools (AC1, AC24, AC26) · unit (fake service)
# Baseline: Given a fake dataset service and project p1 · When each tool's run(args, svc=…, project_id="p1")


def test_download_tool_returns_before_download_ends():
    # G8✅1 · Changed: job never finishes · Then: downloading, future /work paths, "don't read yet" note
    # Demonstrates: the chat isn't blocked
    svc = FakeDatasetService()
    svc.started = STARTED
    shown, result = run(dataset_download.run({"ref": "hf:org/name", "files": ["*.csv"]}, svc=svc, project_id="p1", session_id="s1", approve=never))
    data = json.loads(result)
    assert data["status"] == "downloading" and data["files"][0]["path"].startswith("/work/datasets/")
    assert "Don't read the files until then" in data["note"]
    assert "Downloading in the background" in shown
    assert svc.calls == [("request", "p1", "s1", "hf:org/name", ["*.csv"], False)]


def test_list_tool_shows_status_and_progress():
    # G8✅2 · Changed: ready, downloading (40%), queued · Then: all three, done_bytes, position_in_queue
    # Demonstrates: the model can answer "is it done?"
    svc = FakeDatasetService()
    svc.records = [view("a", "ready"), view("b", "downloading", done=400), view("c", "queued", position=1)]
    shown, result = run(dataset_list.run({}, svc=svc, project_id="p1"))
    data = json.loads(result)
    assert [(d["status"], d["done_bytes"], d["position_in_queue"]) for d in data] == [
        ("ready", None, None), ("downloading", 400, None), ("queued", None, 1)
    ]
    assert "downloading 40%" in shown


def test_search_results_carry_download_ref():
    # G8✅3 · Changed: dataset_search result · Then: ref on HF / Zenodo items, none on DataCite
    # Demonstrates: search → download is one step
    assert search.huggingface_item({"id": "org/name"})["ref"] == "hf:org/name"
    assert search.zenodo_item({"id": 7395559, "metadata": {"title": "x"}})["ref"] == "zenodo:7395559"
    assert "ref" not in search.datacite_item({"id": "10.1/x", "attributes": {"titles": [{"title": "x"}]}})


def test_dataset_tools_are_behind_notebook_switch():
    # G8✅4 · Changed: settings · Then: present only with notebook: True · Demonstrates: the switch controls them
    names = lambda s: {t["function"]["name"] for t in chosen_tools(s)}
    dataset_tools = {"dataset_download", "dataset_list", "dataset_delete"}
    assert dataset_tools <= names({"notebook": True})
    assert not dataset_tools & names({"web_search": True})
    assert not dataset_tools & names({})


def test_download_tool_needs_ref():
    # G8❌1 · Changed: {} · Then: ValueError; service not called
    svc = FakeDatasetService()
    for args in ({}, {"ref": ""}, {"ref": 5}):
        with pytest.raises(ValueError):
            run(dataset_download.run(args, svc=svc, project_id="p1", session_id="s1", approve=never))
    assert svc.calls == []


def test_download_tool_rejects_bad_args():
    # G8❌2 · Changed: files not a list / 21 items / ..; update not a bool · Then: ValueError; service not called
    # Demonstrates: bad arguments stop early
    svc = FakeDatasetService()
    for args in (
        {"ref": "hf:a/b", "files": "*.csv"},
        {"ref": "hf:a/b", "files": [f"f{i}" for i in range(21)]},
        {"ref": "hf:a/b", "files": ["../x"]},
        {"ref": "hf:a/b", "files": ["/abs"]},
        {"ref": "hf:a/b", "files": [3]},
        {"ref": "hf:a/b", "update": "yes"},
    ):
        with pytest.raises(ValueError):
            run(dataset_download.run(args, svc=svc, project_id="p1", session_id="s1", approve=never))
    assert svc.calls == []


def test_no_space_result_explains_sizes():
    # G8❌3 · Changed: service raises NO_SPACE with details · Then: needed/free sizes and available_files in the tool result
    # Demonstrates: the model can explain and retry
    svc = FakeDatasetService()
    svc.error = WorkspaceError(ErrorCode.NO_SPACE, "Not enough disk.", {
        "needed_bytes": 50, "free_bytes": 40, "reserved_bytes": 0, "available_files": [{"path": "a.csv", "size": 50}],
    })
    with pytest.raises(ValueError) as e:
        run(dataset_download.run({"ref": "hf:a/b"}, svc=svc, project_id="p1", session_id="s1", approve=never))
    data = json.loads(str(e.value))
    assert data["error"] == "NO_SPACE" and data["needed_bytes"] == 50 and data["free_bytes"] == 40
    assert data["available_files"] == [{"path": "a.csv", "size": 50}]


# ---- Group S — Security (§5 #4) · unit
# Baseline: negatives only; Given a dataset service with a 300 MB plan


def test_model_cannot_skip_approval_with_arguments(tmp_path):
    # S❌3 · Changed: extra args like {"approved": true} · Then: still asks · Demonstrates: approval can't be bypassed (#4)
    root = tmp_path / "ws"
    store.create_project("P1", root, project_id="p1")
    plan = DatasetPlan("huggingface", "org/name", "Big", "1" * 40, "https://huggingface.co/datasets/org/name", None,
                       [PlannedFile("a.csv", 300_000_000, None, "https://huggingface.co/x")])

    async def resolve(*a, **k):
        return plan

    asked = []

    async def skip(p, size):
        asked.append(size)
        return False

    async def scenario():
        svc = DatasetService(settings=DatasetsSettings(parallel_downloads=0), root=root, free_bytes=FakeFreeDisk(10**12), resolve=resolve)
        await svc.startup_cleanup()
        args = {"ref": "hf:org/name", "approved": True, "approve": True, "force": True}
        shown, result = await dataset_download.run(args, svc=svc, project_id="p1", session_id="s1", approve=skip)
        assert json.loads(result)["error"] == "DECLINED" and "Skipped" in shown
        assert asked == [300_000_000] and svc._jobs == []

    run(scenario())
