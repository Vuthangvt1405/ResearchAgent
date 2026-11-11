"""dataset_search: catalog answers are parsed, merged and ranked. No network."""

import asyncio
import json

import pytest

from researchchat.tools import dataset_search as ds


@pytest.fixture(autouse=True)
def empty_cache():
    ds._cache.clear()


def fake_sources(monkeypatch, **answers):
    """Replace the catalogs: a list is returned, an exception is raised."""
    calls = []

    def make(name, answer):
        async def source(client, query, task, language):
            calls.append((name, query, task, language))
            if isinstance(answer, Exception):
                raise answer
            return answer

        return source

    monkeypatch.setattr(ds, "SOURCES", {n: make(n, a) for n, a in answers.items()})
    return calls


def item(name, description="", **more):
    return {"source": "X", "name": name, "url": f"https://example.com/{name}", "description": description, **more}


def test_huggingface_item_reads_tags():
    got = ds.huggingface_item(
        {
            "id": "org/air-quality",
            "description": "\n\tHourly readings.\n See the full description on the dataset page: https://x",
            "downloads": 1200,
            "lastModified": "2026-05-19T07:48:13.000Z",
            "tags": ["license:cc-by-4.0", "size_categories:10K<n<100K", "format:csv", "region:us"],
        }
    )
    assert got == {
        "source": "Hugging Face",
        "name": "org/air-quality",
        "url": "https://huggingface.co/datasets/org/air-quality",
        "description": "Hourly readings.",
        "license": "cc-by-4.0",
        "size": "10K<n<100K",
        "format": "csv",
        "downloads": 1200,
        "updated": "2026-05-19",
    }


def test_zenodo_item_strips_html_and_sums_files():
    got = ds.zenodo_item(
        {
            "modified": "2025-01-16T07:57:47+00:00",
            "links": {"self_html": "https://zenodo.org/records/1"},
            "stats": {"downloads": 789},
            "files": [{"key": "a.csv", "size": 1_500_000}, {"key": "b.CSV", "size": 500_000}, {"key": "run.py", "size": 0}],
            "metadata": {"title": "Tweets", "description": "<p>Labelled &amp; cleaned</p>", "license": {"id": "cc-by-4.0"}},
        }
    )
    assert got["name"] == "Tweets"
    assert got["description"] == "Labelled & cleaned"
    assert got["size"] == "2.0 MB"
    assert got["format"] == "csv, py"
    assert (got["license"], got["downloads"], got["updated"]) == ("cc-by-4.0", 789, "2025-01-16")


def test_datacite_item_survives_missing_fields():
    got = ds.datacite_item({"attributes": {"doi": "10.1/x", "titles": [{"title": "Sensors"}], "publisher": "Kaggle"}})
    assert got["source"] == "Kaggle"
    assert got["url"] == "https://doi.org/10.1/x"
    assert got["license"] is None and got["description"] == ""


def test_merge_puts_best_keyword_match_first_and_drops_duplicates():
    a = [item("weather"), item("credit card fraud")]
    b = [item("Credit Card Fraud"), item("bank data", "fraud on a credit line")]
    got = ds.merge([a, b], "credit card fraud", limit=10)
    assert [r["name"] for r in got] == ["credit card fraud", "bank data", "weather"]


def test_merge_respects_limit_and_hides_empty_fields():
    got = ds.merge([[item("a", license=None), item("b")]], "a", limit=1)
    assert got == [{"source": "X", "name": "a", "url": "https://example.com/a"}]


def test_run_merges_sources_and_reports_a_failed_one(monkeypatch):
    fake_sources(monkeypatch, One=[item("iris flowers", downloads=1500)], Two=RuntimeError("down"))
    shown, result = asyncio.run(ds.run({"query": "iris"}))
    assert "[iris flowers](https://example.com/iris flowers)" in shown
    assert "1,500 downloads" in shown and "No answer from: Two." in shown
    payload = json.loads(result)
    assert payload["datasets"][0]["name"] == "iris flowers"
    assert payload["note"] == "No answer from: Two."


def test_filters_only_ask_catalogs_that_support_them(monkeypatch):
    calls = fake_sources(monkeypatch, One=[item("iris")], Two=[item("iris two")])
    monkeypatch.setattr(ds, "FILTERABLE", {"One"})
    shown, _ = asyncio.run(ds.run({"query": "iris", "language": "vi"}))
    assert calls == [("One", "iris", "", "vi")]
    assert "iris two" not in shown


def test_run_passes_filters_and_caches_full_answers(monkeypatch):
    calls = fake_sources(monkeypatch, One=[item("iris")])
    monkeypatch.setattr(ds, "FILTERABLE", {"One"})
    asyncio.run(ds.run({"query": "Iris", "task": "tabular-classification", "language": "en"}))
    asyncio.run(ds.run({"query": "iris", "task": "tabular-classification", "language": "en"}))
    assert calls == [("One", "Iris", "tabular-classification", "en")]


def test_partial_answers_are_not_cached(monkeypatch):
    calls = fake_sources(monkeypatch, One=[item("iris")], Two=RuntimeError("down"))
    asyncio.run(ds.run({"query": "iris"}))
    asyncio.run(ds.run({"query": "iris"}))
    assert len(calls) == 4


def test_run_fails_when_every_source_fails(monkeypatch):
    fake_sources(monkeypatch, One=RuntimeError("down"))
    with pytest.raises(ValueError, match="catalogs"):
        asyncio.run(ds.run({"query": "iris"}))


def test_run_needs_a_query_and_handles_no_results(monkeypatch):
    with pytest.raises(ValueError, match="query"):
        asyncio.run(ds.run({"query": " ?? "}))
    fake_sources(monkeypatch, One=[])
    shown, result = asyncio.run(ds.run({"query": "zzz"}))
    assert shown == "No datasets found."
    assert "hint" in json.loads(result)
