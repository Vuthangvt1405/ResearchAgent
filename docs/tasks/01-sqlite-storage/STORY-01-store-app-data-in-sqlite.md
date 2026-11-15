# STORY-01: Store workspace data in SQLite with Alembic migrations

[Epic PRD](../../requirements/01-sqlite-storage/README.md) · [Sprint backlog](README.md) · [Implementation plan](../../plans/sqlite-alembic-storage-plan.md)

**Summary:** Store workspace data in SQLite with Alembic migrations
**Type:** Story | **Epic:** SQLite storage | **Priority:** High | **Labels:** storage, database, tech-debt | **Components:** workspace store, dataset pool, dataset service
**Story points (suggested):** 5 — Complexity M, Uncertainty L, Effort H — three storage modules swap their file I/O for SQL behind unchanged signatures, a new schema and migration setup, old code removed, about 41 tests. All design questions are answered (plan D1–D5). Close to the limit: if the team estimates above 8, split the old-code removal (AC7) into STORY-02.

## User Story

As the **app maintainer**, I want **projects, project datasets and the shared dataset pool index stored in one SQLite database whose schema is managed by Alembic migrations**, so that **changing the data model later is a reviewed migration instead of another hand-written JSON format converter, and the database itself keeps projects and the shared pool consistent**.

As a **developer**, I want **one standard command to create and apply schema changes**, so that **every schema change is reviewable code**.

## Background

Today the app keeps its own records as JSON files in `workspaces/`: `<project>/project.json`, `<project>/datasets.json` and `.dataset-pool.json`. The code reads and writes them by hand, and each data-model change has meant a new file format and a converter (NB-3 → NB-4). Nothing keeps the files consistent with each other: a project can point to a pool entry the index lost, and "which projects use this pool entry" means reading every project's file. The stakeholder asked to move this data into SQLite in the workspace folder, with Alembic for migrations, and confirmed that no backward compatibility is needed.

## Acceptance Criteria

**AC1 — Database created on first start**
Given `workspaces/researchchat.db` doesn't exist
When the app starts (or any code first opens the workspace)
Then the file is created in `workspaces/` and brought to the latest schema before anything reads projects or datasets

**AC2 — Projects work as before**
Given the database is at the latest schema
When a project is created, listed, opened or switched to
Then it behaves exactly as today (same ids, names, sort order and error messages), the data comes from the database, and no `project.json` is written or read

**AC3 — Datasets and the shared pool work as before**
Given the database is at the latest schema
When datasets are requested, linked, listed, deleted or cleaned up
Then it behaves exactly as today (same Datasets tab, same assistant results, same errors), the pool is still shared by all projects, and no `datasets.json` / `.dataset-pool.json` is written or read

**AC4 — A damaged or newer database stops the app clearly**
Given the database file is unreadable, or was made by a newer version of the app
When the app starts
Then startup stops with a message saying what happened and what to do (update the app, or move the file away), and nothing in the database is changed

**AC5 — Developers manage the schema with Alembic**
Given a developer changes the table definitions
When they run `alembic revision --autogenerate -m "…"` and then `alembic upgrade head` from the repo root
Then a migration file is generated and applied to `workspaces/researchchat.db`

**AC6 — Notebooks and files stay files, out of the kernel's reach**
Given any of the above has run
When I look at a project
Then `notebook.ipynb`, the `files/` folder, the pooled dataset files and the dataset links are still ordinary files on disk, and notebook code (the kernel) can't read or change the database

**AC7 — Old formats are gone**
Given the change is done
When the code is searched
Then the JSON-format code, the NB-3 → NB-4 migration and their tests are removed, and nothing refers to them

## Developer Notes

- **Full design:** [implementation plan](../../plans/sqlite-alembic-storage-plan.md), with the schema, test plan (41 tests) and decision log D1–D5. This story is its ticket.
- **Decisions already made (plan Decision log):**
  - **D1:** the dataset pool stays **shared** by all projects; a pool entry is stored once and many projects point to it.
  - **D2:** every table has an **integer primary key plus a unique slug column**, and the slug is still the folder name. Integer keys never leave the storage code.
  - **D3:** **no backward compatibility.** There's no import of old JSON. The NB-3 migration and the JSON-format code are removed (as a separate commit). Existing `workspaces/` data is deleted **once, by hand**, during implementation, after showing the PO the exact list.
  - **D4:** SQLAlchemy ≥ 2.0 and Alembic ≥ 1.13 may be added and installed.
  - **D5:** notebook cells **don't** go into the database.
- **Affected areas (likely):**
  - `researchchat/workspace/store.py`, `datasets_store.py` and `dataset_pool.py`: only the load/save function bodies;
  - a new `researchchat/db/` package and `alembic.ini`;
  - the startup open in `actions.py`;
  - `config.toml` / `config.py`;
  - `requirements.txt`, `README.md`.
- **Dev decisions (from the plan):** SQLAlchemy Core rather than the ORM; one database per workspace root, found from `root`; migrations run automatically at start; timestamps stay ISO-8601 text; foreign keys enforced on every connection; a tampered row is skipped and logged.
- **Security:** keep the database at the `workspaces/` root, which isn't mounted into kernels. Use bound parameters only, and keep the existing id and path checks on every row read.
- **Testing hints:** real SQLite files in `tmp_path`, no mocks. The full existing suite must stay green (297 today, minus the 8 removed migration tests).

## Out of Scope

- Importing or keeping existing workspace data (D3).
- Notebook cells in the database (D5).
- Saving chat history.
- Changing the services to row-by-row updates (a later refactor).
- Two app servers using one workspace at the same time.

## Dependencies

- SQLAlchemy and Alembic added to `requirements.txt` (approved, D4).
- The one-time manual reset of `workspaces/`. The PO confirms the exact list right before deletion.
- [NB-5 plan](../../plans/NB-5-dataset-unpack-preview-plan.md): when picked up, its new pool-file fields become an Alembic migration instead of a JSON format change.

## Open Questions

- None. All were answered in the plan's decision log (D1–D5).
