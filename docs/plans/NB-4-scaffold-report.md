# Scaffold Report: Shared Dataset Pool (NB-4)
Status: Implemented — awaiting review · Plan: [NB-4-dataset-pool-plan.md](NB-4-dataset-pool-plan.md) · Date: 2026-11-13

## 9. Scaffold report

### File tree
```
🆕 researchchat/workspace/dataset_pool.py      DatasetPool, PoolEntry, PoolFile, LinkResult, MigrationReport; all methods raise NotImplementedError
✏️ researchchat/workspace/dataset_service.py   DownloadStarted.from_pool, DatasetRecordView.shared_with, DeleteResult.still_used_by;
                                               Job.pool_entry + waiting_projects; `pool` constructor dependency;
                                               _link_from_pool / _find_shared_job / _join_job / _link_finished_job / _shared_with stubs; TODOs in request, delete, cancel, startup_cleanup
✏️ researchchat/workspace/datasets_store.py    ProjectDataset (format 2); load_project_datasets / save_project_datasets / manifest_format stubs
✏️ researchchat/workspace/kernels.py           TODO for the read-only /pool mount (not added: see note 1)
✏️ researchchat/workspace/service.py           DatasetProps.shared_with
✏️ researchchat/tools/dataset_download.py, dataset_list.py, dataset_delete.py   TODOs for from_pool / shared_with / still_used_by
✏️ app.py                                      TODO: migration runs inside startup_cleanup
✏️ README.md                                   "Shared dataset pool (in progress)" section + layout line
🆕 tests/test_dataset_pool.py                  G11 (9 tests, incl. G11❌3 @docker) + G14 (6)
✏️ tests/test_dataset_service.py               G4✅4, G6✅9, G7✅2, G7✅4, G7✅5
✏️ tests/test_workspace_kernels.py             G11✅4
✏️ tests/test_datasets_store.py                TODO on S❌5 (existing test kept green; see note 3)
```

### Build and test result
- `python -m compileall researchchat app.py tests`: ✅ passes
- `ruff check` on the new files: ✅ clean (the repo already had 59 ruff findings in other files; none are new)
- `pytest`: **21 failed (all new, Red on purpose), 273 passed**, the same 273 as before the scaffold

### Notes / deviations from the plan
1. **The kernel mount is a TODO, not an argument yet.** Docker refuses a bind mount whose source folder is missing, and nothing creates `.dataset-pool/` until the pool code exists. Adding the argument now would break every kernel start.
2. **`public/elements/Notebook.jsx` was not changed.** It's only a shim that draws nothing. The "Also used by N other projects" line belongs in `public/panel/src/components/DatasetCard.tsx` (details and the delete confirm). That file isn't on the plan's list, so I left it alone. Please confirm that the plan should list DatasetCard.tsx instead of Notebook.jsx.
3. **S❌5:** the existing test is `test_delete_ignores_tampered_manifest` in `tests/test_datasets_store.py`, not `…manifests`. I added a TODO instead of making it Red, so that an existing test doesn't break.
4. The new TypedDict keys are declared as required. Existing code doesn't fill them yet. That's harmless at runtime because there's no type checker in the repo, and the TODOs cover filling them in.

### TODO map
| TODO | File:line | AC / SEC / test |
|---|---|---|
| entry_dir, kernel_link_target | `dataset_pool.py:83, 95` | SEC23, G11❌2 |
| make_entry_id, find_entries | `dataset_pool.py:89, 117` | AC30, G11✅5 |
| load_index, save_index, rebuild_index | `dataset_pool.py:102, 107, 112` | G11❌4 |
| is_file_unchanged, recheck_file | `dataset_pool.py:124, 129` | SEC16, G11❌1 |
| link_files | `dataset_pool.py:134` | AC15, AC16, AC28, G11✅1–2, G6✅9 |
| unlink_dataset | `dataset_pool.py:139` | SEC23, S❌5 |
| projects_using, remove_unused_entry | `dataset_pool.py:146, 151` | AC25, D7, G7✅2, G7✅5, G11❌5 |
| migrate, migrate_project, move_into_pool | `dataset_pool.py:158, 163, 168` | AC29, SEC24, A14, G14 |
| format 2 store | `datasets_store.py:342, 348, 354` | AC29, G14 |
| request (pool first) | `dataset_service.py:286` | AC15, AC16, AC30 |
| delete via pool | `dataset_service.py:488` | AC25, G7✅2, G7✅5 |
| _link_from_pool | `dataset_service.py:495` | AC15, AC16, AC28, G4✅4 |
| _find_shared_job, _join_job, _link_finished_job | `dataset_service.py:500, 505, 510` | AC17, SEC9, G11✅3, G7✅4 |
| _shared_with | `dataset_service.py:515` | AC25 |
| cancel per project | `dataset_service.py:520` | AC27, G7✅4 |
| migration at start | `dataset_service.py:554`, `app.py:55` | AC29, D8 |
| /pool mount | `kernels.py:236` | AC18, SEC12, G11✅4 |
| tool results | `dataset_download.py:147`, `dataset_list.py:43`, `dataset_delete.py:72` | AC15, AC25 |

### Suggested first test
`test_links_never_point_outside_pool` (G11❌2). It needs only `make_entry_id`, `entry_dir` and `kernel_link_target`, which are pure path rules, and every later link test builds on them. After that, `test_second_project_links_pool_files_without_download` (G11✅1).

## 10. Verification

| # | Check | Result |
|---|---|---|
| V1 | Files match the plan's list | ✅, except Notebook.jsx not touched (note 2); test_datasets_store.py got one TODO line (note 3) |
| V2 | Endpoints (tool/action results) match §4.2 | ✅ result fields declared; behaviour is TODO |
| V3 | DTO fields match §4.3 | ✅ from_pool, shared_with (view + props), still_used_by, freed_bytes comment |
| V4 | Schema (pool index, format 2) matches §3.3, nothing migrated | ✅ PoolEntry/PoolFile/ProjectDataset; no data touched |
| V5 | Security wiring (§5) | ✅ pool lock exists; read-only mount is a TODO (note 1) |
| V6 | Planned tests exist with the exact names | ✅ planned 21 / found 21 (S❌5 kept as a TODO) |
| V7 | No logic leaked | ✅ new methods only hold TODO comments and raise NotImplementedError; the only new code is field declarations and the `pool` dependency |
| V8 | Build passes; new tests fail; existing tests pass | ✅ 21 failed / 273 passed |

Please verify before I implement any logic:
- ☐ File locations and class/method names look right for our codebase
- ☐ Tool result fields (`from_pool`, `shared_with`, `still_used_by`) are what you want
- ☐ DTO and schema fields (PoolEntry, PoolFile, ProjectDataset) are final
- ☐ The UI change goes in DatasetCard.tsx instead of Notebook.jsx (note 2)
- ☐ The test list is complete: is any negative or security case missing?
- ☐ The TODO map covers all the work

Reply "verified" to start implementing logic test by test, or tell me what to change in the scaffold.

Verified by the user on 2026-11-13.

## 11. Implementation report

### Files
| | File | Change |
|---|---|---|
| 🆕 | `researchchat/workspace/dataset_pool.py` | pool index (+ rebuild), entry ids, relative links, link checks, users and cleanup, NB-3 migration |
| ✏️ | `researchchat/workspace/dataset_service.py` | pool-first `request` (AC30 version choice), shared jobs with per-project waiters, per-project cancel, delete via the pool, app-wide partials, migration at start |
| ✏️ | `researchchat/workspace/datasets_store.py` | format 2 (`ProjectDataset`); format 1 kept for the migration only; `link_path`; dead NB-3 helpers removed |
| ✏️ | `researchchat/workspace/kernels.py` | `run_arguments` builder; read-only pool mount (folder created first) |
| ✏️ | `researchchat/workspace/service.py` | `DatasetProps.shared_with` |
| ✏️ | `researchchat/tools/dataset_download.py`, `dataset_list.py`, `dataset_delete.py` | "ready from the shared pool" text; read-only note for the model; "also in N other projects"; delete confirm with 0 freed when shared |
| ✏️ | `public/panel/src/types.ts`, `components/DatasetCard.tsx`, `test/fixtures.ts` | "Also used by N other projects" in details and the delete confirm |
| 🆕 | `public/panel/src/components/DatasetShared.test.tsx` | 2 tests |
| ✏️ | `public/build/notebook-panel.js` | rebuilt bundle |
| ✏️ | `app.py`, `README.md` | comment; "Shared dataset pool" section |
| 🆕/✏️ | `tests/test_dataset_pool.py`, `test_dataset_service.py`, `test_datasets_store.py`, `test_dataset_tools.py`, `test_workspace_kernels.py` | NB-4 tests; NB-3 tests read format 2 through a `records()` helper |

### Coverage
| AC / Security | Tests (all green) |
|---|---|
| AC15 | G4✅4, G11✅1 |
| AC16 | G11✅2 |
| AC17 | G11✅3, G7✅4 |
| AC18 | G11✅4, G11❌3 (docker) |
| AC25 | G7✅2, G7✅5, panel `DatasetShared` ✅1–2 |
| AC27 | G7✅4 |
| AC28 | G6✅9 (and G6✅8 for lost pooled bytes) |
| AC29 | G14✅1–3, G14❌1–5 |
| AC30 | G11✅5 |
| SEC9 races | G11✅3, G7✅4, G11❌5 |
| SEC12 shared data | G11✅4, G11❌3 |
| SEC16 changed pool files | G11❌1 |
| SEC23 links | G11❌2, S❌5 |
| SEC24 migration | G14 |

### Results
- `pytest` (Docker running): **297 passed** (273 before + 21 planned NB-4 + 3 added below), 0 failed; the dataset tests also pass with real DNS blocked
- panel: `tsc --noEmit` clean; `vitest run` **39 passed** (37 + 2); `vite build` ok
- `ruff` on the new and changed modules: no new findings (the ones left were already there: `datetime.UTC`, `asyncio.TimeoutError`, `try/except/pass` in cancel, `subprocess.run` check)

### Tests added during implementation (after review)
- `test_migration_resumes_after_a_crash_inside_a_project` (G14❌4): a file already moved, no index. The index is now saved before the first move, and a rebuilt entry gets its catalog details back from the NB-3 record.
- `test_project_skipped_by_migration_is_never_overwritten` (G14❌5): a project whose start-up migration failed is migrated when it's first read, never read as empty and overwritten.
- `test_update_while_downloading_is_busy`: NB-3's BUSY guard for `update: true` during a download is back.

Also fixed after review: the migration checks a file's checksum **before** moving it (a changed file stays in place, G14❌1) and refuses linked folders on the way; `from_pool` is true only when nothing at all was fetched; `_plan_request` is split into named steps with typed dataclasses (`DownloadRequest`, `FetchPlan`) and no flag arguments; the pool tests now fake DNS like the service tests.

### NB-3 tests changed (behaviour the plan replaces)
- All service tests read `datasets.json` format 2 through `records()` (pool entry joined in) instead of `ds.load_records`.
- `env.partial()` is now the app-wide `.dataset-partial/`.
- `test_missing_files_are_downloaded_again_only` (G6✅8) deletes the pooled file instead of the link (R6).
- `test_delete_removes_folder_and_record` expects `still_used_by: 0`; `test_model_delete_declined_keeps_dataset` expects the 3-argument confirm (R9).
- `test_make_id_suffixes_clashes` (was `…_and_reuses_same_source`): the same dataset is now found through its pool entry.
- `test_delete_ignores_tampered_manifests` (S❌5) rewritten for format 2 and a crafted `pool_entry`.

### Review (2026-11-13)

A reviewer pass over the working tree, against the plan's ACs and §5 security table:

| Check | Result |
|---|---|
| Every AC (15–18, 25, 27–30) has a named test, and it passes | ✅ `pytest` → **297 passed, 0 failed** (Docker running, so G11❌3 ran too) |
| The plan's file list matches the diff | ✅ plus the R2 deviation (`DatasetCard.tsx` instead of `Notebook.jsx`) and `public/panel/src/test/fixtures.ts` |
| Pool-first `request()` re-checks the pool before linking (SEC16) | ✅ `ensure_ready_files_intact` → `recheck_file` hashes a changed file |
| Links are only ever written by the app (SEC23) | ✅ `link_target()` builds the only target; `is_linked()` compares the link text; `entry_dir()` refuses any id that isn't a generated slug |
| The pool is read-only in the kernel (SEC12) | ✅ `run_arguments` mounts `target=/.dataset-pool,readonly`; G11❌3 proves writes fail |
| One lock for index, linking and cleanup (SEC9) | ✅ `DatasetPool.lock` is the service's only lock; `remove_unused_entry()` re-checks the users under it |
| Migration is resumable and keeps a backup (SEC24) | ✅ index saved before the first move; `datasets.json.v1` kept; G14❌2/❌4 |
| `ruff` on the changed modules | ✅ 56 findings vs. 58 before the change — no new ones |
| Panel (`tsc --noEmit`, `vitest`) | ✅ clean; **39 passed** |

### Not done / not checked
- Not checked in the running app (starting a second server here would break the one you have open).
- The start-up migration runs in a worker thread, but re-checking a changed pooled file (SEC16) still hashes it inside the request. That's rare, but a changed multi-GB file would pause the app while it's hashed.
- Windows hosts are untested: making symlinks there may need Developer Mode or admin rights.
- The "Also used by N other projects" line in the panel is only verified by the component tests, not in a browser.
