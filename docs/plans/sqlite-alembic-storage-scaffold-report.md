# Scaffold Report: Store app data in SQLite, with Alembic migrations
Status: Verified — implemented (see plan §11) · Plan: [sqlite-alembic-storage-plan.md](sqlite-alembic-storage-plan.md) · Story: [STORY-01](../tasks/01-sqlite-storage/STORY-01-store-app-data-in-sqlite.md) · Date: 2026-11-15

## 9. Scaffold report

### 9.1 File tree

```
alembic.ini                                         🆕 CLI config (script_location, file_template, logging)
config.toml                                         ✏️ [notebook] database_file = "researchchat.db"
requirements.txt                                    ✏️ + sqlalchemy>=2.0, alembic>=1.13
researchchat/
├── config.py                                       ✏️ DATABASE_FILE
└── db/
    ├── __init__.py                                 🆕 package docstring
    ├── schema.py                                   🆕 metadata + 5 tables, 2 indexes, named constraints (complete)
    ├── engine.py                                   🆕 database_for, create_workspace_engine, upgrade_to_latest,
    │                                                  check_database_readable (all NotImplementedError), DatabaseUnusable, database_path
    └── migrations/
        ├── env.py                                  🆕 Alembic environment (app connection or CLI)
        ├── script.py.mako                          🆕 Alembic's template, typed in the repo's style
        └── versions/0001_initial_schema.py         🆕 DDL from plan §3.3 + downgrade (NOT run)
tests/
├── test_database.py                                🆕 G1 (7) + S1 (2): 9 failing tests
├── test_workspace_store.py                         ✏️ + G2: 8 failing tests
├── test_datasets_store.py                          ✏️ + G3: 12 failing tests
├── test_dataset_pool.py                            ✏️ + G4: 9 failing tests
└── test_dataset_service.py                         ✏️ + G5: 2 failing tests
```

Installed into `.venv` (D4): SQLAlchemy 2.1.8, Alembic 1.20.1 (and its dependency Mako 1.4.3).

**Deliberately not touched yet.** These files are in plan §4.1, but changing them now would break the app:

| File | Why it waits | When |
|---|---|---|
| `researchchat/workspace/store.py`, `datasets_store.py`, `dataset_pool.py` | Their load/save **bodies** are what changes. Replacing them with `NotImplementedError` would break all 297 passing tests and the running app. Their signatures don't change, so there's no new shape to scaffold | implementation, commit 1 |
| `researchchat/workspace/actions.py` | Calling `database_for(...)` at import would raise `NotImplementedError` in every test that imports actions | implementation, commit 1 |
| Removal list (plan §4.1 "Removed code") and the 8 NB-3 migration tests | That's commit 2, after commit 1 is green | implementation, commit 2 |
| Tests the plan rewrites in place (`test_startup_marks_stale_jobs_failed`, the `manifest_path` assert in `test_dataset_service.py`, `test_corrupt_manifest_is_set_aside`, `test_corrupt_pool_index_is_rebuilt`, `test_delete_ignores_tampered_manifests`, `test_new_project_has_empty_notebook_and_files_dir`) | They test today's JSON behaviour and still pass; their DB replacements exist as new failing tests, and the old ones are deleted or rewritten when the bodies swap | implementation |
| `README.md` | Text about the new storage; written once it works | implementation |

### 9.2 Build and test result

| Check | Command | Result |
|---|---|---|
| Compile | `python -m compileall -q researchchat tests` | ✅ pass |
| Import + tables | `import researchchat.db.engine, researchchat.db.schema` | ✅ 5 tables: `pool_entries, pool_files, project_dataset_files, project_datasets, projects` |
| Alembic sees the migration | `alembic heads` | ✅ `0001 (head)` |
| Lint, new files | `ruff check researchchat/db tests/test_database.py` | ✅ all checks passed |
| Lint, touched existing files | `ruff check` before (HEAD) vs after, per file | ✅ same counts (pre-existing findings only, none added) |
| Tests | `pytest -q` | ✅ **297 passed** (no existing test broken), **40 failed**, which are exactly the new skeletons, each by `pytest.fail("TODO(…)")` |
| No DB writes | search for `researchchat.db*` | ✅ none created; the migration was not run |

The schema's DDL was rendered **without a database** (`CreateTable(...).compile(dialect=sqlite)`), and it matches `0001_initial_schema.py` table for table: same columns, nullability, defaults, the `CHECK`s, `UNIQUE`s, foreign keys (`CASCADE` / `RESTRICT`) and both indexes. G1✅3 will prove it against a real upgrade.

**Test count vs plan.** Two of the planned tests already exist under the same name, so no skeleton was added for them: G2✅3 `test_duplicate_name_gets_unique_id` (unchanged) and G5✅1 `test_startup_marks_stale_jobs_failed` (rewritten in place). G5❌2 `test_no_code_references_removed_formats` was planned as a check step and is now a real pytest (grep, plus vulture in V7). The plan now counts **42 tests**; 42 − 2 existing = **40 new failing tests**.

### 9.3 TODO map

`grep -rn "TODO(" researchchat/db tests/test_database.py tests/test_workspace_store.py tests/test_datasets_store.py tests/test_dataset_pool.py tests/test_dataset_service.py` lists all of it.

| TODO | File:line | Belongs to |
|---|---|---|
| open, check, upgrade, cache per root | `researchchat/db/engine.py:38` (`database_for`) | AC1, AC4 · G1✅1, G1✅2, G1❌2, G1❌3 |
| engine + PRAGMAs on every connection | `researchchat/db/engine.py:44` (`create_workspace_engine`) | AC1, SEC4 · G1❌1 |
| `upgrade head`, refuse unknown revision | `researchchat/db/engine.py:50` (`upgrade_to_latest`) | AC1, AC4, SEC6 · G1✅1, G1✅2, G1❌2 |
| damaged file → `DatabaseUnusable` | `researchchat/db/engine.py:56` (`check_database_readable`) | AC4 · G1❌3 |
| G1 tests (7) | `tests/test_database.py:19, 27, 35, 43, 51, 59, 67` | AC1, AC4, AC5, SEC4, SEC6 |
| S1 tests (2) | `tests/test_database.py:80, 88` | SEC1, SEC2 |
| G2 tests (8) | `tests/test_workspace_store.py:181–237` | AC2, AC6, SEC3 |
| G3 tests (12) | `tests/test_datasets_store.py:124–212` | AC3, SEC3–SEC5 |
| G4 tests (9) | `tests/test_dataset_pool.py:447–511` | AC3, SEC3–SEC5 |
| G5 tests (2) | `tests/test_dataset_service.py:1267, 1275` | AC3, AC7 |
| shared baseline setup per group | `tests/test_database.py:10, 71`, `tests/test_workspace_store.py:172`, `tests/test_datasets_store.py:115`, `tests/test_dataset_pool.py:438`, `tests/test_dataset_service.py:1258` | each group's Baseline line |
| **not yet in code** (see 9.1): SQL bodies of `store.create_project / list_projects / get_project / _unique_id` | `researchchat/workspace/store.py` | AC2 · G2 |
| ″ `datasets_store.load_project_datasets / save_project_datasets` | `researchchat/workspace/datasets_store.py` | AC3 · G3 |
| ″ `DatasetPool.load_index / save_index / projects_using` | `researchchat/workspace/dataset_pool.py` | AC3 · G4 |
| ″ `database_for(WORKSPACES_DIR)` at startup | `researchchat/workspace/actions.py` | AC1, AC4 |
| ″ removal list + 8 NB-3 tests (commit 2) | plan §4.1 "Removed code" | AC7 · G5 |
| ″ one-time manual reset of `workspaces/` (ask first) | plan §3.3 "Existing data" | D3, SEC7 |

### 9.4 Suggested first test

**G1✅1 `test_first_open_creates_database_at_head`** (`tests/test_database.py:14`). It forces `create_workspace_engine`, `upgrade_to_latest` and `database_for` to exist, and everything else builds on them. Then G1❌1 (PRAGMAs), then G1✅3 (the migration matches `schema.py`).

## 10. Verification

### 10a. Self-verification

| # | Check | Result |
|---|---|---|
| V1 | Every file in "Files affected" exists; no extras | ⚠️ All **new** files exist. Of the modified files, `config.toml`, `config.py`, `requirements.txt` and the 4 test files are done; `store.py`, `datasets_store.py`, `dataset_pool.py`, `actions.py` and `README.md` are deliberately untouched (9.1: their change is the logic itself). No extra files. The other `git status` entries (`.claude/…`, `docs/requirements/`, `docs/tasks/`) predate this scaffold |
| V2 | Endpoints match §4.2 | ✅ n/a: no endpoints change, and no Chainlit action was touched |
| V3 | DTOs match §4.3 | ✅ no DTO or dataclass changed; the row ↔ dataclass mapping lands in the I/O bodies |
| V4 | Migration DDL matches §3.3, not executed | ✅ matches (offline DDL render vs `0001`); no database file exists |
| V5 | Security wiring from §5 | ✅ DB path is `<workspaces root>/researchchat.db` (`engine.database_path`), outside the kernel mounts (SEC1); `CONNECTION_PRAGMAS` holds `foreign_keys=ON` (SEC4); `RESTRICT` FK in schema and migration (SEC4) |
| V6 | Every planned test exists with the exact name | ✅ planned 42 = 40 new skeletons + 2 existing same-name tests (9.2); names generated from the plan's tables, so they match exactly |
| V7 | No logic leaked | ✅ `engine.py` bodies are TODO + `NotImplementedError`; `schema.py` and `0001` are declarative. One note: `migrations/env.py` has Alembic's standard wiring (app connection vs CLI, offline mode refused). That's framework boilerplate, not app logic |
| V8 | Build passes; new tests fail; existing pass | ✅ compile + lint pass; 40 new fail; 297 existing pass |

### 10b. Please verify before I implement any logic

- ☐ File locations and names look right: `researchchat/db/{schema,engine}.py`, `researchchat/db/migrations/`, `alembic.ini` at the repo root
- ☐ The deliberately untouched files (9.1) are OK to change only during implementation
- ☐ Migration DDL is correct (column types, nullability, `CASCADE` / `RESTRICT`, the two indexes, constraint names)
- ☐ The test list is complete (any missing negative or security case?)
- ☐ The TODO map covers all the work, including the manual `workspaces/` reset, which I'll confirm with you before deleting anything

Reply "verified" to start implementing logic test by test, or tell me what to change in the scaffold.
