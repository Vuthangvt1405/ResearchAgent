"""Tests for parse_ref, the catalog resolvers and the downloader host rule (NB-3 plan §7: G1, G2, G3, S❌1).

No network: catalogs are httpx.MockTransport handlers, and host lookups are faked
(names resolve to a public address, IP literals to themselves).
"""

import asyncio

import httpx
import pytest

from researchchat.workspace import ErrorCode, WorkspaceError
from researchchat.workspace import dataset_sources as src
from tests.conftest import catalog_client, fake_lookup

SHA = "a" * 40


@pytest.fixture(autouse=True)
def no_dns(monkeypatch):
    monkeypatch.setattr(src, "lookup_host", fake_lookup)


def run(coro):
    return asyncio.run(coro)


def code_of(fn) -> str:
    with pytest.raises(WorkspaceError) as e:
        fn()
    return e.value.code


# ---- Group 1 — Parse refs (AC1, AC13, SEC1) · unit
# Baseline: Given no state · When parse_ref("hf:org/name")


def test_parse_ref_huggingface():
    # G1✅1 · Then: ("huggingface", "org/name") · Demonstrates: search refs map to a source
    assert src.parse_ref("hf:org/name") == ("huggingface", "org/name")


def test_parse_ref_zenodo():
    # G1✅2 · Changed: zenodo:7395559 · Then: ("zenodo", "7395559") · Demonstrates: Zenodo refs work
    assert src.parse_ref("zenodo:7395559") == ("zenodo", "7395559")


def test_parse_ref_accepts_dataset_page_urls():
    # G1✅3 · Changed: dataset page URLs · Then: same tuples · Demonstrates: the model can pass the URL it was given
    assert src.parse_ref("https://huggingface.co/datasets/org/name") == ("huggingface", "org/name")
    assert src.parse_ref("https://huggingface.co/datasets/org/name/tree/main") == ("huggingface", "org/name")
    assert src.parse_ref("https://zenodo.org/records/7395559") == ("zenodo", "7395559")


def test_parse_ref_rejects_empty():
    # G1❌1 · Changed: "", "   " · Then: BAD_REF · Demonstrates: no download without a dataset
    for ref in ("", "   ", None, 5):
        assert code_of(lambda: src.parse_ref(ref)) == ErrorCode.BAD_REF


def test_parse_ref_rejects_unknown_prefix():
    # G1❌2 · Changed: kaggle:x, doi:10.1/x · Then: UNSUPPORTED_SOURCE · Demonstrates: only catalogs with a file API
    for ref in ("kaggle:x", "doi:10.1/x"):
        assert code_of(lambda: src.parse_ref(ref)) == ErrorCode.UNSUPPORTED_SOURCE


def test_parse_ref_rejects_other_hosts():
    # G1❌3 · Changed: other hosts / http · Then: BAD_REF · Demonstrates: other hosts never reach the downloader
    for ref in (
        "https://evil.example/datasets/a/b",
        "http://huggingface.co/datasets/a/b",
        "https://huggingface.co.evil.example/datasets/a/b",
        "https://user@huggingface.co/datasets/a/b",
    ):
        assert code_of(lambda: src.parse_ref(ref)) == ErrorCode.BAD_REF


def test_parse_ref_rejects_bad_ids():
    # G1❌4 · Changed: path tricks / bad ids · Then: BAD_REF · Demonstrates: ids can't carry path tricks
    for ref in ("hf:../etc", "hf:a/b/c", "hf:./x", "hf:a/..", "hf:noslash", "zenodo:12a", "hf:o/" + "n" * 200):
        assert code_of(lambda: src.parse_ref(ref)) == ErrorCode.BAD_REF


# ---- Group 2 — Resolve Hugging Face (AC1, AC4, AC13) · unit (MockTransport)
# Baseline: Given a public dataset with README.md, .gitattributes, data/train.csv, data/test.csv
# · When resolve("huggingface", id, files=None)


def hf_entry(path, size=10, lfs=False):
    entry = {"type": "file", "path": path, "size": size, "oid": "1" * 40}
    if lfs:
        entry["lfs"] = {"oid": "b" * 64, "size": size}
    return entry


BASE_TREE = [
    {"type": "directory", "path": "data"},
    hf_entry(".gitattributes"),
    hf_entry("README.md", 5),
    hf_entry("data/train.csv", 100, lfs=True),
    hf_entry("data/test.csv", 40, lfs=True),
]


class HF:
    """A fake Hugging Face API; records every URL asked for."""

    def __init__(self, pages=None, info=None, status=200):
        self.pages = pages or [BASE_TREE]
        self.info = {"id": "org/name", "sha": SHA, "private": False, "gated": False, "cardData": {"license": "mit"}}
        self.info.update(info or {})
        self.status = status
        self.requested: list[str] = []
        self.next_override: str | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requested.append(url)
        if self.status != 200:
            return httpx.Response(self.status)
        if "/tree/" in url:
            n = int(request.url.params.get("cursor", "0"))
            headers = {}
            if n + 1 < len(self.pages):
                nxt = self.next_override or f"https://huggingface.co/api/datasets/org/name/tree/{SHA}?recursive=true&cursor={n + 1}"
                headers["link"] = f'<{nxt}>; rel="next"'
            return httpx.Response(200, json=self.pages[n], headers=headers)
        return httpx.Response(200, json=self.info)


def hf_resolve(api: HF, files=None, max_files=500):
    async def go():
        async with catalog_client(api) as client:
            return await src.resolve("huggingface", "org/name", files, max_files=max_files, client=client)

    return run(go())


def test_hf_plan_lists_files_with_size_checksum_and_revision():
    # G2✅1 · Then: 3 files (no .gitattributes), sizes, sha256: for LFS, revision = sha, URLs pinned to it
    # Demonstrates: the plan is exact and repeatable
    plan = hf_resolve(HF())
    assert [(f.path, f.size) for f in plan.files] == [("README.md", 5), ("data/train.csv", 100), ("data/test.csv", 40)]
    assert plan.files[0].checksum is None  # git blob sha1 is not a content hash
    assert plan.files[1].checksum == "sha256:" + "b" * 64
    assert plan.revision == SHA
    assert plan.files[1].url == f"https://huggingface.co/datasets/org/name/resolve/{SHA}/data/train.csv"
    assert plan.license == "mit" and plan.url == "https://huggingface.co/datasets/org/name"


def test_hf_plan_filters_by_glob():
    # G2✅2 · Changed: files=["*.csv"] · Then: the 2 csv files · Demonstrates: large datasets can be narrowed
    plan = hf_resolve(HF(), files=["*.csv"])
    assert [f.path for f in plan.files] == ["data/train.csv", "data/test.csv"]
    assert [f.path for f in hf_resolve(HF(), files=["train.csv"]).files] == ["data/train.csv"]


def test_hf_file_list_follows_pages():
    # G2✅3 · Changed: list over 2 pages (link rel="next") · Then: files of both pages
    # Demonstrates: big datasets aren't cut off at 1,000
    api = HF(pages=[[hf_entry("a.csv")], [hf_entry("b.csv")]])
    assert [f.path for f in hf_resolve(api).files] == ["a.csv", "b.csv"]


def test_hf_filter_keeps_count_under_limit_on_big_repo():
    # G2✅4 · Changed: 3,000 files, filter matches 50 · Then: those 50; allowed
    # Demonstrates: a filter makes huge datasets usable
    pages = [[hf_entry(f"p{p}/f{i}.{'csv' if p == 1 and i < 50 else 'txt'}") for i in range(1000)] for p in range(3)]
    plan = hf_resolve(HF(pages=pages), files=["*.csv"], max_files=500)
    assert len(plan.files) == 50


def test_hf_name_uses_pretty_name_or_repo_id():
    # G2✅5 · Changed: card pretty_name / none · Then: pretty name / repo id; source_id = repo id
    # Demonstrates: readable title, stable key
    pretty = hf_resolve(HF(info={"cardData": {"pretty_name": "twitter financial news"}}))
    assert pretty.name == "twitter financial news" and pretty.source_id == "org/name"
    plain = hf_resolve(HF(info={"cardData": {}}))
    assert plain.name == "org/name" and plain.source_id == "org/name"


def test_hf_gated_dataset_is_refused():
    # G2❌1 · Changed: gated: "auto" · Then: NOT_PUBLIC + landing URL, no file request
    # Demonstrates: terms-gated data isn't fetched
    api = HF(info={"gated": "auto"})
    with pytest.raises(WorkspaceError) as e:
        hf_resolve(api)
    assert e.value.code == ErrorCode.NOT_PUBLIC
    assert e.value.details["url"] == "https://huggingface.co/datasets/org/name"
    assert not any("/tree/" in u for u in api.requested)


def test_hf_missing_dataset_is_not_found():
    # G2❌2 · Changed: API 404 / 401 · Then: NOT_FOUND · Demonstrates: private and missing look the same
    for status in (404, 401):
        assert code_of(lambda: hf_resolve(HF(status=status))) == ErrorCode.NOT_FOUND


def test_hf_filter_matching_nothing():
    # G2❌3 · Changed: files=["*.parquet"] · Then: NO_FILES + available names
    # Demonstrates: the model gets what it can choose from
    with pytest.raises(WorkspaceError) as e:
        hf_resolve(HF(), files=["*.parquet"])
    assert e.value.code == ErrorCode.NO_FILES
    assert e.value.details["available_files"] == ["README.md", "data/train.csv", "data/test.csv"]


def test_hf_unsafe_file_paths_are_refused():
    # G2❌4 · Changed: ../../x, /abs, a\\b · Then: refused, nothing planned
    # Demonstrates: catalog data can't write outside the folder
    for bad in ("../../x", "/abs", "a\\b"):
        with pytest.raises(WorkspaceError):
            hf_resolve(HF(pages=[[hf_entry("ok.csv"), hf_entry(bad)]]))


def test_hf_too_many_files():
    # G2❌5 · Changed: 3 pages of 1,000, no filter · Then: TOO_MANY_FILES after page 1; pages 2–3 never requested
    # Demonstrates: max_files holds and stops early
    api = HF(pages=[[hf_entry(f"p{p}/f{i}") for i in range(1000)] for p in range(3)])
    assert code_of(lambda: hf_resolve(api, max_files=500)) == ErrorCode.TOO_MANY_FILES
    assert [u for u in api.requested if "/tree/" in u and "cursor=" in u] == []


def test_hf_next_page_link_to_other_host_is_refused():
    # G2❌6 · Changed: next link to another host / http · Then: refused; never requested
    # Demonstrates: page links can't steer requests
    for nxt in ("https://evil.example/page2", "http://huggingface.co/api/datasets/org/name/tree/x?cursor=1"):
        api = HF(pages=[[hf_entry("a.csv")], [hf_entry("b.csv")]])
        api.next_override = nxt
        with pytest.raises(WorkspaceError):
            hf_resolve(api)
        assert all("cursor" not in u and "evil" not in u for u in api.requested)


# ---- Group 3 — Resolve Zenodo (AC1, AC13) · unit (MockTransport)
# Baseline: Given open record 7395559 with creditcard.csv + md5 · When resolve("zenodo", "7395559")


def zenodo_record(**changes):
    record = {
        "id": 7395559,
        "links": {"self_html": "https://zenodo.org/records/7395559"},
        "metadata": {"title": "Credit card fraud", "access_right": "open", "license": {"id": "cc-by-4.0"}},
        "files": [{"key": "creditcard.csv", "size": 150, "checksum": "md5:" + "c" * 32}],
    }
    for key, value in changes.items():
        if key in ("access_right",):
            record["metadata"][key] = value
        else:
            record[key] = value
    return record


def zenodo_resolve(handler, files=None):
    async def go():
        async with catalog_client(handler) as client:
            return await src.resolve("zenodo", "7395559", files, max_files=500, client=client)

    return run(go())


def test_zenodo_plan_lists_files_with_md5():
    # G3✅1 · Then: 1 file, size, md5:…, …/content URL, title as name, licence
    # Demonstrates: Zenodo files are planned exactly
    plan = zenodo_resolve(lambda r: httpx.Response(200, json=zenodo_record()))
    assert [(f.path, f.size, f.checksum) for f in plan.files] == [("creditcard.csv", 150, "md5:" + "c" * 32)]
    assert plan.files[0].url == "https://zenodo.org/api/records/7395559/files/creditcard.csv/content"
    assert (plan.name, plan.license, plan.revision) == ("Credit card fraud", "cc-by-4.0", None)


def test_zenodo_restricted_record_is_refused():
    # G3❌1 · Changed: restricted / embargoed · Then: NOT_PUBLIC · Demonstrates: only open data
    for access in ("restricted", "embargoed"):
        handler = lambda r, a=access: httpx.Response(200, json=zenodo_record(access_right=a))
        assert code_of(lambda: zenodo_resolve(handler)) == ErrorCode.NOT_PUBLIC


def test_zenodo_missing_record():
    # G3❌2 · Changed: 404 / 410 · Then: NOT_FOUND · Demonstrates: a missing record fails clearly
    for status in (404, 410):
        assert code_of(lambda: zenodo_resolve(lambda r, s=status: httpx.Response(s))) == ErrorCode.NOT_FOUND


def test_zenodo_record_without_files():
    # G3❌3 · Changed: files: [] · Then: NO_FILES · Demonstrates: metadata-only records fail clearly
    handler = lambda r: httpx.Response(200, json=zenodo_record(files=[]))
    assert code_of(lambda: zenodo_resolve(handler)) == ErrorCode.NO_FILES


def test_zenodo_unsafe_file_key():
    # G3❌4 · Changed: key ../x · Then: refused · Demonstrates: same traversal rule as HF
    handler = lambda r: httpx.Response(200, json=zenodo_record(files=[{"key": "../x", "size": 1}]))
    with pytest.raises(WorkspaceError):
        zenodo_resolve(handler)


# ---- Group S — Security (§5 #1) · unit
# Baseline: negatives only; Given MockTransport


def test_downloader_only_starts_at_catalog_hosts(tmp_path):
    # S❌1 · Changed: plan URL host not huggingface.co / zenodo.org · Then: refused before any request
    # Demonstrates: SSRF allow-list (#1)
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(200, content=b"x")

    async def nothing(n):
        pass

    async def go(url):
        async with catalog_client(handler) as client:
            await src.stream_file(src.PlannedFile("x", 1, None, url), tmp_path / "x", client=client, on_bytes=nothing, stall_timeout=1)

    for url in ("https://evil.example/x", "http://huggingface.co/x", "https://127.0.0.1/x"):
        with pytest.raises(WorkspaceError):
            run(go(url))
    assert requested == []
    assert not (tmp_path / "x").exists()
