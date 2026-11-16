# Scaffold Report: Show data files created in the notebook in the Datasets tab

Status: Implemented — awaiting review · Plan: [PCD-1-created-datasets-plan.md](PCD-1-created-datasets-plan.md) · Story: [STORY-01](../tasks/02-project-created-datasets/STORY-01-list-created-datasets.md) · Branch: `feat/PCD-1-created-datasets` · Date: 2026-11-16

## 9. Scaffold report

### 9.1 File tree

```
docs/plans/PCD-1-0002_created_datasets.py.draft   🆕 migration 0002, full DDL + downgrade, PARKED outside versions/ (D9), not run
researchchat/
├── config.py                                     ✏️ CREATED_DATA_EXTENSIONS (A4)
├── tools/dataset_list.py                         ✏️ _created_line (NotImplementedError); TODO for DEFINITION text
└── workspace/
    ├── created_datasets_store.py                 🆕 FileSnapshot, CreatedDataset, make_created_id, kernel_file_path,
    │                                                load/insert/update/delete_created_dataset (all NotImplementedError)
    ├── created_datasets.py                       🆕 ScanChanges, is_data_file, scan_data_files, compare_with_stored,
    │                                                is_file_present, missing_notice, CreatedDatasets (sync, panel_rows,
    │                                                model_views, owns, delete, missing_names); all NotImplementedError
    ├── service.py                                ✏️ DatasetOrigin, DatasetProps.origin, AfterRun, after_run param,
    │                                                run_lock() (NotImplementedError), TODO at the hook call site in _run
    ├── dataset_service.py                        ✏️ DatasetRecordView.origin, `created` dependency, sync_created
    │                                                (NotImplementedError; owns the datasets_rev bump); TODOs in
    │                                                list_for_model, delete, panel_state
    ├── datasets_store.py                         ✏️ TODO markers only, at the replace-all delete and the load query
    └── actions.py                                ✏️ toast_missing_created_files (NotImplementedError); TODOs for wiring,
                                                     open_for_session and nb_switch_project
public/panel/src/
├── types.ts                                      ✏️ DatasetOrigin, DatasetProps.origin (optional, see 9.5)
├── components/DatasetCard.tsx                    ✏️ SOURCES.created = "Created by myself"; isCreated,
│                                                    createdDeleteText, createdMissingText (throw); TODOs in the render
├── lib/loadCode.ts                               ✏️ createdLoadCode (throws); TODO in loadCode
├── components/DatasetCard.test.tsx               ✏️ + G8✅2–✅3, G9✅2–✅3, S3❌1: 5 failing tests
└── lib/actions.test.tsx                          ✏️ + G5✅1–✅3, G5❌1–❌2: 5 failing tests
tests/
├── test_created_datasets.py                      🆕 G1, G3✅1–✅3, G4, G5✅4 (docker), G6, G7 (4), G8 (3), G9 (5), G11, S1❌1–❌4, S3❌2: 48
├── test_created_datasets_store.py                🆕 G3❌1, G10✅1/❌2/❌3/❌4/❌6, S1❌5: 7
├── test_database.py                              ✏️ + G10✅2–✅3 (migration up/down): 2
├── test_datasets_store.py                        ✏️ + G10❌1, G10❌5: 2
├── test_dataset_tools.py                         ✏️ + G8✅4: 1
└── test_workspace_service.py                     ✏️ + G2, G7 toasts (5), S2: 13
```

### 9.2 Build and test result

| Check | Command | Result |
|---|---|---|
| Compile | `python -m compileall -q researchchat tests app.py` | ✅ pass |
| Import | `import researchchat.workspace.actions, researchchat.tools.dataset_list` | ✅ (no import cycle: `created_datasets` imports `DatasetRecordView` only under `TYPE_CHECKING`) |
| Migration chain unchanged | `alembic heads` | ✅ `0001 (head)`; 0002 is parked (D9) |
| Lint | `ruff check researchchat tests app.py`, before vs after | ✅ same 54 pre-existing findings, none added (one import-order issue I introduced was fixed) |
| Python tests | `pytest -q -m "not docker"` | ✅ **295 passed** (all existing, none broken), **72 failed** = the new skeletons, each by `pytest.fail("TODO(…)")`; the 73rd (G5✅4) is `@pytest.mark.docker`, collected and deselected here |
| Panel typecheck | `npm run typecheck` | ✅ pass |
| Panel tests | `npx vitest run` | ✅ **39 passed** (all existing), **10 failed** = the new skeletons, each by `expect.fail("TODO(…)")` |
| No DB writes | `workspaces/researchchat.db*` timestamps | ✅ unchanged since 2026-11-15; the migration was not run |

Tests: planned 83 / found 83 (73 Python + 10 Vitest).

### 9.3 TODO map

`grep -rn "TODO(AC\|TODO(SEC" researchchat public/panel/src tests` lists all remaining work.

| TODO | File:line | Covers |
|---|---|---|
| is_data_file | `researchchat/workspace/created_datasets.py:53` | AC5 · G4 |
| scan_data_files (no links, skip hidden + datasets/) | `created_datasets.py:59` | AC1, AC10, SEC1, SEC8 · G4❌4, G6 |
| compare_with_stored (re-save, rename by inode+size+mtime) | `created_datasets.py:66` | AC4, AC12, SEC10 · G3, G11 |
| ScanChanges.has_changes | `created_datasets.py:47` | AC4 · G2❌1, G3✅3 |
| is_file_present | `created_datasets.py:73` | AC7, SEC1 · G7✅1, G7❌4 |
| missing_notice (toast text) | `created_datasets.py:79` | AC11, SEC6 · G7✅5, S3❌2 |
| CreatedDatasets.sync | `created_datasets.py:99` | AC1, AC2, AC4, AC12, AC13 · G1, G3, G11 |
| CreatedDatasets.panel_rows | `created_datasets.py:104` | AC1, AC3, AC7 · G8✅1, G8❌2 |
| CreatedDatasets.model_views | `created_datasets.py:109` | AC7, AC9 · G7✅1, G8✅4 |
| CreatedDatasets.owns | `created_datasets.py:114` | AC8, SEC3 · G9❌1, S2❌1 |
| CreatedDatasets.delete (run lock, re-check, unlink) | `created_datasets.py:119` | AC8, SEC1, SEC2 · G9, S1❌1–❌4 |
| CreatedDatasets.missing_names | `created_datasets.py:125` | AC11 · G7✅3, G7❌1, G11✅3 |
| make_created_id | `researchchat/workspace/created_datasets_store.py:44` | AC3 · G8❌1 |
| kernel_file_path | `created_datasets_store.py:50` | AC1, AC6 · G1✅1 |
| load_created_datasets (skip tampered rows) | `created_datasets_store.py:56` | AC3, SEC4 · G10✅1, S1❌5 |
| insert_created_dataset | `created_datasets_store.py:62` | AC1 · G1✅1, G3❌1, G10❌2–❌4 |
| update_created_dataset | `created_datasets_store.py:68` | AC4, AC12 · G3✅1, G11✅1 |
| delete_created_dataset | `created_datasets_store.py:74` | AC8 · G9✅1 |
| scope replace-all save to downloaded | `researchchat/workspace/datasets_store.py:189` | AC3 · G10❌1 |
| scope load to downloaded | `datasets_store.py:208` | AC3 · G10❌5 |
| DatasetProps.origin values | `researchchat/workspace/service.py:91` | AC3 · G8✅1 |
| NotebookService.run_lock | `service.py:205` | AC8, SEC2 · S1❌4 |
| call after_run before the push | `service.py:347` | AC1, AC2, AC9 · G2 |
| DatasetRecordView.origin values | `researchchat/workspace/dataset_service.py:130` | AC9 · G8✅4 |
| sync_created: scan + bump datasets_rev |  `dataset_service.py:654` | AC1, AC2 · G2✅1, G2❌1, G3✅3 |
| list_for_model appends created views | `dataset_service.py:661` | AC9 · G2✅3, G8✅4 |
| delete routes created ids | `dataset_service.py:676` | AC8, SEC3 · G9✅1, S2❌1 |
| panel_state sets origin, appends created rows | `dataset_service.py:937` | AC3 · G8✅1 |
| wire after_run and run_lock | `researchchat/workspace/actions.py:81` | AC1, AC2, SEC2 · G2✅1 |
| toast after nb_switch_project | `actions.py:228` | AC11 · G7✅4 |
| toast_missing_created_files | `actions.py:238` | AC11, SEC6 · G7✅3–✅5, G7❌1 |
| open_for_session: sync once + toast | `actions.py:245` | AC11, A6 · G7✅3, G7❌2 |
| _created_line, DEFINITION text | `researchchat/tools/dataset_list.py:29, 33` | AC9 · G8✅4 |
| createdLoadCode, loadCode branch | `public/panel/src/lib/loadCode.ts:41, 46` | AC6, SEC5 · G5 |
| isCreated, createdDeleteText, createdMissingText | `public/panel/src/components/DatasetCard.tsx:20, 26, 32` | AC3, AC7, AC8 · G8✅2, G9✅2 |
| card render: missing text, hide facts, file path, delete text | `DatasetCard.tsx:108, 113, 141, 178` | AC1, AC3, AC6, AC7, AC8 |
| move migration into versions/ + schema.py columns | `docs/plans/PCD-1-0002_created_datasets.py.draft` | D2, D9 · G10 |
| turn foreign keys off around the batch rebuild (data-loss risk) | `PCD-1-0002_created_datasets.py.draft:38` | D2 · G10✅2, G10✅3 |

### 9.4 Suggested first test

**G10✅1 `test_created_row_round_trips`** (`tests/test_created_datasets_store.py`). Everything else stands on storage, so start here: move the parked migration to `researchchat/db/migrations/versions/0002_created_datasets.py`, add the same columns and constraints to `schema.py`, change the two `== ("0001",)` asserts in `test_database.py` to `"0002"`, scope `datasets_store.py` (G10❌1, ❌5), then implement `insert_created_dataset` + `load_created_datasets`. The existing `test_upgrade_matches_schema` (`compare_metadata`) catches any mismatch between `schema.py` and the migration. After that, G1✅1 (`test_new_csv_is_listed_as_created_and_ready`) is the first behaviour test.

### 9.5 Deliberately not done yet, and deviations from the plan

| Item | What and why | When |
|---|---|---|
| `schema.py` + migration in `versions/` (D9) | `database_for()` upgrades every workspace to head at app start and in every test, so a 0002 in `versions/` would rebuild your real `workspaces/researchchat.db` before the code using it exists, and break the two head asserts. The DDL is complete in the `.draft` file | first implementation step (9.4) |
| Wiring in `actions.py` and the `_run` hook call | `service.after_run = datasets.created.sync` and the toast at chat start would call `NotImplementedError` on every cell run and every new chat. Signatures and TODOs are in place | when G2 / G7 go green |
| `datasets_store.py` scoping | It's logic (a WHERE clause), so only TODO markers now | with G10❌1, ❌5 |
| `DatasetProps.origin` in TypeScript is **optional** | The plan says required. Making it required would need `public/panel/src/test/fixtures.ts`, which isn't on the files list. The server always sends it, and absent means "downloaded". Can be made required when the fixture is updated | your call (checklist) |
| Toast tests in `tests/test_workspace_service.py`, not `tests/test_panel_ui.py` | `test_panel_ui.py` only does static checks on panel sources; the toast is sent from `actions.py`, which `test_workspace_service.py` already tests with `FakeSession`. `test_panel_ui.py` is unchanged | — |
| `NotebookService.run_lock()` added | Public accessor so `CreatedDatasets.delete` can hold the run lock (SEC2) without reaching into `_run_lock`; `service.py` was on the list | — |
| `public/build/notebook-panel.js`, `.css` not rebuilt | The panel has no new behaviour yet, so the bundle would be the same; rebuilt when the card logic lands | implementation |

## 10. Verification

### 10a. Self-verification

| # | Check | Result |
|---|---|---|
| V1 | Every file in "Files affected" exists; no extra files | ✅ with the deviations in 9.5: `schema.py` and the migration are parked as one `.draft` (D9); `test_panel_ui.py` and `public/build/*` unchanged. `git status` shows no other changed files besides the `.claude/*` edits that were there before this session and the `check_mermaid.sh` fix you asked for |
| V2 | Actions / tool / push match §4.2 | ✅ `ds_delete` reused (no new `FIELDS` entry); `dataset_list` keeps its name; toast is `toast_missing_created_files` |
| V3 | DTO fields match §4.3 | ✅ `origin: DatasetOrigin` on `DatasetProps` (Python + TS) and `DatasetRecordView`; created-row fields in `CreatedDataset` / `FileSnapshot`. TS `origin` is optional (9.5) |
| V4 | Migration DDL matches §3.3 and was **not** executed | ✅ nullable `pool_entry_pk`; `origin` (default `'downloaded'`), `path`, `size_bytes`, `mtime_ns`, `inode`; `origin_known`, `origin_shape`, `uq (project_pk, path)`; downgrade deletes created rows first. Not in `versions/`, `alembic heads` = 0001, DB untouched |
| V5 | Security wiring from §5 present | ✅ `RunLockFor` injected into `CreatedDatasets`; `NotebookService.run_lock`; project only from the session (unchanged `actions.dispatch`); `NOTICE_NAME_MAX_CHARS`; `POOL_LINKS_DIR` skip constant |
| V6 | Every planned test exists, exact names, count matches | ✅ planned 83 / found 83 (73 Python, 10 Vitest), generated from the §7 tables |
| V7 | No logic leaked | ✅ new bodies are TODO + `NotImplementedError` / `throw new Error("Not implemented…")`; `__init__`s only store dependencies; the only data added is constants (`CREATED_DATA_EXTENSIONS`, `SOURCES.created`, prefixes) |
| V8 | Build passes; new tests fail; existing pass | ✅ compile, ruff (no new findings), tsc pass; 295 + 39 existing pass; 72 + 10 new fail by their TODO; 1 docker test deselected |

### 10b. Please verify before I implement any logic

- ☐ File locations and class/method names look right for our codebase
- ☐ The action/tool contract is final: `ds_delete` reused, `dataset_list` gains created lines, toast via `send_toast(…, "warning")`
- ☐ DTO fields are final: `origin` on `DatasetProps` / `DatasetRecordView`; TS `origin` optional or required?
- ☐ Migration DDL in the `.draft` is correct (nullability, `origin_shape` check, unique `(project_pk, path)`, downgrade)
- ☐ The test list is complete — any missing negative or security case?
- ☐ The TODO map covers all the work

Reply "verified" to start implementing logic test-by-test, or tell me what to change in the scaffold.

## 11. Implementation

Verified by you on 2026-11-16 ("Verified, implement"). Built test-first in the order of §9.4: storage, scan and rename rules, service wiring, panel. Nothing committed.

### 11.1 Results

| Check | Result |
|---|---|
| Python tests (`pytest -m "not docker"`) | ✅ **368 passed**: 295 existing + 72 planned + 1 added (below); 0 failed |
| Docker test G5✅4 (`pytest -m docker tests/test_created_datasets.py`) | ✅ passed against a real kernel: kernel code writes `Iris.csv`, the scan lists it, the card's load code reads it back (`(2, 2)`) |
| Other Docker tests (32, kernels) | not run this time; `NotebookService._run` only gained a guarded hook call |
| Panel (`npm run typecheck`, `npx vitest run`) | ✅ 49 passed (39 existing + 10 planned) |
| Ruff vs `HEAD` | ✅ no new findings (same 54 pre-existing) |
| Vulture on changed modules | ✅ only the pre-existing `step_title(args)` signature |
| Panel bundle | ✅ rebuilt: `public/build/notebook-panel.js`, `.css` |
| Mutation spot-checks | ✅ each made tests fail, then restored: symlink rules off (4 fail), rename match off (3), unscoped downloaded save (1), delete following a link (2), Licence row shown on created cards (1 Vitest) |
| Your `workspaces/researchchat.db` | untouched (still revision 0001). **It is upgraded to 0002 the next time you start the app.** |
| Remaining `TODO(` / not-implemented in PCD-1 code | none |

### 11.2 Changes beyond the scaffold

| Change | Why |
|---|---|
| `researchchat/db/engine.py`: `upgrade_to_latest` runs migrations with foreign keys off (`foreign_keys_off`), then `PRAGMA foreign_key_check` (`refuse_broken_foreign_keys`) | Not on the plan's file list, but needed for D2. SQLite ignores the PRAGMA inside a transaction, so it can't live in the migration. Without it, 0002 empties `project_dataset_files` |
| Added test `test_upgrade_with_foreign_keys_on_would_empty_file_lists` (`tests/test_database.py`) | Shows the data loss above is real, so the guard can't be removed by accident |
| Migration moved from `docs/plans/PCD-1-0002_created_datasets.py.draft` to `researchchat/db/migrations/versions/0002_created_datasets.py`; `schema.py` columns added; `test_database.py` head asserts `"0001"` → `"0002"` | First step of §9.4 (D9) |
| `datasets_store._slug` renamed to public `slug_of` | `make_created_id` reuses it (CLAUDE.md: no private cross-module use) |
| `compare_with_stored(stored, found)` dropped the `present_paths` parameter | "Gone" is simply "not found by this scan" |
| `actions.toast_missing_created_files(dataset_service, project_id, send_toast)` and new `list_created_datasets_now` | Dependencies passed in, so tests run without a Chainlit context. `open_for_session` scans once (A6), then toasts; `nb_switch_project` toasts |
| `DatasetService.delete` returns `freed_bytes` = the file's size for created files | Shown in the existing delete result shape |
| `CreatedDatasets` takes a `clock` | Lets G3✅1 check that "updated" really moves forward |
| G8❌2 uses a 250-char name, not 500 | Linux file names stop at 255 bytes; still above the 200 cap |
| `tests/test_dataset_tools.py` `view()` helper gained `"origin": "downloaded"` | The real `DatasetRecordView` always has it now |
| TS `DatasetProps.origin` stays optional | As verified in the scaffold (absent = downloaded) |

### 11.3 Not checked

- The app itself was not started: starting it here would upgrade your real database and could clash with a server you run (`.files/` is shared). Suggested manual check: start the app, ask "create an iris dataset", then run your own `df.to_csv('results.csv')` cell; rename one file and delete the other outside the tab, then open a new chat to see the toast.

