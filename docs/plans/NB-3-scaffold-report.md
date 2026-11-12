# Scaffold Report: Background Dataset Download & Management (NB-3)
Status: Implemented — awaiting review · Plan: [NB-3-dataset-download-plan.md](NB-3-dataset-download-plan.md) · Date: 2026-11-12

## 9. Scaffold report

### File tree

```
app.py                                  ✏️ 2 TODO comments only (startup cleanup, finish notes); app runs as before
config.toml                             ✏️ [datasets] section (5 settings)
researchchat/config.py                  ✏️ DATASETS_* constants read from [datasets]
researchchat/workspace/__init__.py      ✏️ 9 new ErrorCodes; WorkspaceError(code, message, details=None)
researchchat/workspace/service.py       ✏️ DatasetProps; NotebookProps.datasets / datasets_rev; DatasetState; NotebookService(datasets=…)
researchchat/workspace/actions.py       ✏️ ChatRegistry, `chats`, `datasets` service, ds_delete / ds_cancel in FIELDS + dispatch
researchchat/workspace/datasets_store.py   🆕 DatasetFile, DatasetRecord, manifest / id / path / swap functions
researchchat/workspace/dataset_sources.py  🆕 PlannedFile, DatasetPlan, parse_ref, resolvers, stream_file
researchchat/workspace/dataset_service.py  🆕 DatasetsSettings, DTO TypedDicts, DatasetService
researchchat/tools/dataset_download.py  🆕 DEFINITION, read_args, ask_approval, run
researchchat/tools/dataset_list.py      🆕 DEFINITION, run
researchchat/tools/dataset_delete.py    🆕 DEFINITION, ask_approval, run
researchchat/tools/__init__.py          ✏️ TODO only: tools not registered yet
researchchat/tools/dataset_search.py    ✏️ TODO only: `ref` on HF / Zenodo items
public/elements/Notebook.jsx            ✏️ DatasetsSection stub (returns null, not rendered); TODO in newer()
tests/conftest.py                       ✏️ catalog_client, FakeFreeDisk, FakeChats, FakeDatasetService
tests/test_datasets_store.py            🆕 G6❌1, S❌2, S❌5 (3)
tests/test_dataset_sources.py           🆕 G1, G2, G3, S❌1 (24)
tests/test_dataset_service.py           🆕 G4, G5, G6 (except ❌1), G7, G9, G10, S❌4, S❌6 (45)
tests/test_dataset_tools.py             🆕 G8, S❌3 (8)
```

Not touched: `README.md` (it documents working behaviour, so it changes when the feature works), `tests/test_settings.py`, `tests/test_read_page.py`, `tests/test_dataset_search.py`, `researchchat/workspace/panel.py`.

Already in the working tree before the scaffold: your uncommitted docstring edit in `app.py` and the untracked `docs/` plan files. They were left as they were. The branch is still `feat/NB-2-dataset-search-tool`. Nothing was committed and no branch was switched.

**Plan revisions found while scaffolding**

1. **The tools aren't registered yet.** Adding the three tools to `_NOTEBOOK_MODULES` now would offer the model tools that only fail. Registration is a TODO in `tools/__init__.py`, covered by G8✅4. `test_each_switch_adds_its_own_tools` changes when they're registered.
2. **Nothing new is called from live code.** `NotebookService._props`, `open_for_session`, `close_for_session`, `on_chat_start` and `on_message` only have TODO comments. `service.datasets` is not wired to `datasets.panel_state` yet. That keeps the app and all 129 existing tests working.
3. **`ChatRegistry` lives in `actions.py`.** §2.1 says "`actions.py`/`panel.py`", but `panel.py` isn't in the Files Affected list, so it stays unchanged.
4. **`test_read_page.py` stays unchanged.** §4.1 lists it as modified, but §7 says it stays unchanged. Also, `tests/test_dataset_search.py` and `tests/test_settings.py` stay as they are for now. G8✅3 (search `ref`) and G8✅4 (registration) live in `tests/test_dataset_tools.py`, so each test is counted once.
5. **Test file mapping**, which the plan didn't spell out: store → G6❌1, S❌2, S❌5; sources → G1–G3, S❌1; service → G4–G7 (minus G6❌1), G9, G10, S❌4, S❌6; tools → G8, S❌3.
6. **`DatasetService` gets an extra injection point, `client_factory`.** Tests can supply the MockTransport client for background jobs. `describe()` was added for the Delete / Keep prompt, which needs the name and size before deleting.
7. **Test gap for your check:** the `make_id` clash rule (`-2`, `-3`, reusing the id for the same source) has no planned test.

### Build and test result

| Check | Command | Result |
|---|---|---|
| Compile | `python -m compileall -q researchchat app.py tests` | ✅ pass |
| Import | `python -c "import app"` | ✅ pass; `FIELDS` has `ds_cancel`, `ds_delete` |
| Tests | `pytest -q -m "not docker"` | ✅ **80 failed (all new, on purpose), 129 passed (all existing), 30 deselected (Docker)** |
| Test names | planned names vs `def test_…` in the 4 new files | ✅ 80 / 80, identical |
| App | preview on port 8001 | ✅ chat and Notebook panel render; no console or server errors |

### TODO map

`grep -rn "TODO(" researchchat app.py public tests/conftest.py` lists the remaining work.

| Where | Plan refs | Work |
|---|---|---|
| `datasets_store.py:63` | AC21 | `size_bytes` |
| `datasets_store.py:72–89` | AC3, AC24, AC28, SEC2, SEC6, G6❌1 | manifest path, load (corrupt → `.bad`), atomic save, find |
| `datasets_store.py:98` | AC1, SEC2 | `make_id` |
| `datasets_store.py:104–128` | SEC2, SEC8, G2❌4, G3❌4, S❌2 | `safe_relpath`, `dataset_dir`, `partial_dir`, `file_path`, `kernel_path` |
| `datasets_store.py:137–155` | AC12, AC25, AC28, SEC8, SEC18, SEC19, G6✅3–4, G6❌3, S❌5 | missing check, remove, update swap, startup recovery |
| `dataset_sources.py:43–49` | AC1, AC13, SEC1, SEC2, G1, S❌1 | `parse_ref`, `check_download_url` |
| `dataset_sources.py:62–84` | AC1, AC4, AC13, SEC1–3, SEC13, G2, G3 | `resolve`, Hugging Face + Zenodo resolvers, `match_files` |
| `dataset_sources.py:100` | AC6, AC9, SEC1, SEC3, SEC5, G5 | `stream_file` |
| `dataset_service.py:139` | AC1, AC5, AC7, AC10–13, SEC3, SEC4, SEC9, SEC18, G4, G6 | `request` |
| `dataset_service.py:146–161` | AC24–27, SEC6, SEC8, SEC9, G7, G8✅2 | `list_for_model`, `describe`, `delete`, `cancel` |
| `dataset_service.py:168–178` | AC3, AC6, AC8, AC9, AC14, SEC3, SEC5, SEC18, SEC19, G4❌4, G5, G6❌3, G10 | `startup_cleanup`, `wait_idle`, `_run_job` |
| `dataset_service.py:185–195` | AC3, AC8, AC9, AC21, SEC10, SEC11, SEC16, SEC17, G9✅2, G10✅3, G10✅5 | `panel_state`, `take_notes`, `drop_notes` |
| `service.py:213` | AC8, AC21, SEC16, G9✅2 | `datasets` / `datasets_rev` in `_props` |
| `actions.py:39–48` | AC3, AC9, SEC11, SEC17, G10 | `ChatRegistry.register` / `unregister` / `send` |
| `actions.py:66` | AC8, G9✅2 | wire `service.datasets = datasets.panel_state` |
| `actions.py:162–165` | AC25, AC27, SEC6, G7✅3, G9 | `ds_delete`, `ds_cancel` |
| `actions.py:206–211` | AC3, SEC11, SEC17, G10✅5 | register / unregister the chat |
| `app.py:38` | SEC18, G6❌3 | start `startup_cleanup` |
| `app.py:76` | AC3, AC9, SEC10, G10✅3 | one-turn finish note (like `LIMIT_NOTE`) |
| `tools/dataset_download.py:50–75` | AC1, AC2, AC4, AC5, AC7, AC12, SEC4, G4✅2, G4❌1, G8 | title, `read_args`, Download / Skip, `run` |
| `tools/dataset_list.py:23` | AC24, AC28, G8✅2 | `run` |
| `tools/dataset_delete.py:31–39` | AC26, SEC4, SEC6, G7❌3, S❌4 | Delete / Keep, `run` |
| `tools/__init__.py:17` | AC1, AC24, AC26, G8✅4 | register the 3 tools |
| `tools/dataset_search.py:84, 100` | AC1, G8✅3 | `ref` on HF / Zenodo items |
| `Notebook.jsx:49, 400` | AC8, AC21, AC25, AC27, SEC12, SEC16 | `datasets_rev` in `newer()`; Datasets section |
| `tests/conftest.py:110–136` | G7❌3, G8, G10 | fake chats and fake dataset service |

### Suggested first test

**G1✅1 `test_parse_ref_huggingface`** in `tests/test_dataset_sources.py`. It is pure, needs no fixtures, and makes `parse_ref` exist. Continue through the rest of Group 1, then the store helpers (`safe_relpath`, `make_id`), which every later group depends on.

## 10. Verification

### 10a. Self-verification

| # | Check | Result |
|---|---|---|
| V1 | Files match "Files affected", and nothing else changed | ✅ `git status`: 10 modified + 10 new files, all in the plan's list. Deliberately unchanged (revisions 1, 3, 4): `README.md`, `panel.py`, `test_settings.py`, `test_read_page.py`, `test_dataset_search.py`. The `app.py` docstring edit and the `docs/` files were already there before the scaffold |
| V2 | Endpoints match §4.2 | ✅ tools `dataset_download` (ref, files, update), `dataset_list`, `dataset_delete` (dataset_id); actions `ds_delete` / `ds_cancel` `{dataset_id: str}` |
| V3 | DTOs match §4.3 | ✅ `DownloadStarted`, `DatasetRecordView`, `DeleteResult`, `DatasetProps` (13 fields), `NotebookProps.datasets` / `datasets_rev`, manifest dataclasses |
| V4 | Schema (`datasets.json`) matches §3.3, and nothing was written | ✅ `DatasetRecord` / `DatasetFile` fields match; no `datasets.json` or dataset folder was created |
| V5 | Security wiring from §5 | ✅ project comes from the session in `dispatch`; `FIELDS` allow-list for `ds_*`; `approve` injection on download / delete; `DATASET_ID_RE`; `USER_AGENT` without tokens; HTTPS / host checks are TODOs |
| V6 | Every planned test exists, with the exact name | ✅ planned 80 / found 80, names identical |
| V7 | No logic leaked | ✅ new method bodies contain only TODOs and not-implemented errors. The exceptions are wiring, not rules: constructors store their dependencies (with a `DatasetsSettings()` default), `step_title`s return constant strings, and the plan's `disk_free` default calls `shutil.disk_usage(...).free`. The `ds_*` dispatch branches raise |
| V8 | Build passes, new tests fail, existing tests pass | ✅ compile and import pass; 80 failed / 129 passed / 30 deselected |

### 10b. Please verify before I implement any logic

```
☐ File locations and class/method names look right for our codebase
☐ Tool names, arguments and the ds_delete / ds_cancel payloads are what you want
☐ DTO fields (DownloadStarted, DatasetRecordView, DatasetProps) are final
☐ datasets.json record fields are correct
☐ The test list is complete (any missing case? e.g. the make_id clash rule)
☐ TODO map covers all the work
```

Reply "verified" to start implementing logic test by test, or tell me what to change in the scaffold.


## 11. Implementation report

Verified by the user on 2026-11-12 ("ok let's implement"). Implemented test group by test group, in the plan's order.

### Result

| Check | Result |
|---|---|
| Tests | `pytest -q -m "not docker"`: **212 passed**, 30 deselected (Docker). That's 129 existing + 83 new: store 4, sources 24, service 47, tools 8 |
| Compile / import | `python -m compileall -q researchchat app.py tests` and `python -c "import app"` pass |
| Real downloads | One tiny dataset per catalog, run into a scratch workspace (not `workspaces/`): `hf:julien-c/titanic-survival` (2 files, 43.5 KB, CDN redirect followed, sha256 checked) and `zenodo:10396807` (4 files, 12.2 KB, md5 checked). Both `ready` with the right chat messages |
| Panel | App preview: the Datasets section renders ready (with details), downloading (progress + licence), queued ("2nd in queue") and failed (reason + Delete confirm) rows, using injected rows. A Delete click sends one `ds_delete` action and gets props back. No console or server errors |
| Leftover TODOs | none: `grep -rn "TODO(" researchchat app.py public tests/conftest.py` is empty |

Not verified: a full download started by the model in a live chat (it needs an OpenRouter call). The tool, service and panel were each checked as described above.

### AC and security coverage

Every AC and security row in plan §7's coverage tables has passing tests, with the same test names as the plan. #12 (XSS) was checked by hand: the panel renders catalog text as React text only, and links go through `safeHref`.

### Plan revisions made while implementing

1. **Extra tests (83 total):**
   - `test_make_id_suffixes_clashes_and_reuses_same_source` (store) covers the id clash rule from §3.3.
   - `test_linked_dataset_folders_are_never_followed` and `test_failed_update_keeps_old_version_ready` (service) cover revisions 11 and 12.
2. **Pinned revisions:** `resolve(..., revision=)` lets an existing Hugging Face dataset be re-planned at its stored commit (needed for a new `files` selection without silently updating, AC12). `file_url()` rebuilds download URLs from catalog ids, so missing or failed files can be fetched again without a catalog call.
3. **Own URL check:** `dataset_sources.check_download_url` is async and HTTPS-only, with its own `lookup_host`. `read_page.check_public_url` allows http and blocks the event loop on DNS, so it isn't reused. Tests fake `lookup_host`, so they never touch DNS.
4. **More injection points on `DatasetService`:** `resolve` (fake catalogs in the disk/approval tests), `progress_interval` (0 in tests) and `close()`.
5. **Store additions:** `remove_partial` and `partial_root`, for failed/cancelled cleanup. The empty `.dataset-partial/` folder is removed too.
6. **Declined download** is a normal tool result (`{"error": "DECLINED", …}`), not a tool failure; other errors reach the model as JSON with their details (e.g. `NO_SPACE` sizes).
7. **New rule:** `update: true` while the same dataset is downloading returns `BUSY`, so an update never runs next to another job on the same folder.
8. **Cancel keeps finished files:** cancelling a new selection of an existing dataset removes only the unfinished files; the record is removed only when nothing is left (A3 for new downloads).
9. **Finish notes** are kept only when the chat message was actually delivered (the chat is still open, A13).
10. **Existing tests changed:** `test_settings.py` (3 tools registered behind the Notebook switch) and `test_dataset_search.py` (`ref` on Hugging Face items). `README.md` now has a "Dataset downloads" section.
11. **Linked folders are refused (security fix found in review):** `files/` is read-write at `/work`, so notebook code could replace `files/datasets` (or `files/datasets/<id>`) with a symlink to a host folder. The old check resolved through the link, so downloads and deletes would have followed it. `dataset_dir` now refuses a linked `files/datasets` or `<id>` folder. `remove_dataset_dir` unlinks a linked `<id>` without following it, and touches nothing when `files/datasets` itself is a link.
12. **A failed update no longer leaves the dataset `failed`:** the old version stays complete, and the next request without `update` marks it `ready` again. A real `ENOSPC` raised outside the stream (for example when a file is closed) is reported as "disk full".
13. **Progress pushes every 1 s** (not 0.25 s), since each push re-sends the whole panel props.

### Known limitations

- **Pre-existing panel behaviour:** when an action's reply has the same notebook `version` as the panel, `newer()` keeps the pushed props, so a rejected `ds_delete` / `ds_cancel` (e.g. `BUSY`) can lose its error banner. Notebook actions already behave this way. The dataset list itself is merged by `datasets_rev`.
- **Accepted risk (§5 #21, N1):** there is no cap on queued downloads.

Nothing is committed. The branch is still `feat/NB-2-dataset-search-tool`, and `app.py` mixes the user's earlier docstring edit with the NB-3 hooks.
