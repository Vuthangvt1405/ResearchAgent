# Epic PRD — SQLite storage

**Suggested total:** 5 points · **Backlog:** [docs/tasks/01-sqlite-storage/](../../tasks/01-sqlite-storage/README.md) · **Plan:** [sqlite-alembic-storage-plan.md](../../plans/sqlite-alembic-storage-plan.md)

## Summary

Move the app's own records (projects, project datasets, the shared dataset pool index) from hand-written JSON files into one SQLite database in the workspace folder, with Alembic managing the schema and its migrations. Notebooks, project files and pooled dataset files stay files on disk.

## Background

Requested 2026-11-15: "change this project to using SQLite, combining with Alembic for migrations… the database placed in the workspace folder". Today `workspaces/` holds `project.json` and `datasets.json` per project, plus `.dataset-pool.json` for the whole app. Each data-model change has needed a new file format and a converter, and nothing keeps the files consistent with each other.

## Requirement Analysis

| Item | Finding |
|---|---|
| Actors | App maintainer, developer (no change visible to researchers) |
| Goals | One database with managed migrations; same behaviour for users |
| Business value | Cheaper, safer data-model changes; the database guarantees projects and the shared pool stay consistent *(assumed)* |
| Rules (stated by PO) | SQLite + Alembic; the database lives in the workspace folder; the pool stays shared (D1); integer key + unique slug (D2); no backward compatibility, old data may be dropped (D3); SQLAlchemy and Alembic may be installed (D4); notebooks stay files (D5) |
| Data | Projects, project datasets and their files, pool entries and their files |
| Ambiguities | None open; all answered in the plan's decision log |

## Estimation Log

| Candidate story | Complexity | Uncertainty | Effort | Points | Action |
|---|---|---|---|---|---|
| Store workspace data in SQLite (first draft, with JSON import and NB-3 support) | M | M | H | 8 | Re-estimated after PO answers |
| ↳ STORY-01: without backward compatibility (D3), notebooks out (D5) | M | L | H | 5 | ✅ Keep as one story: the three record types share one schema and migration, so they can't ship apart. If the team estimates above 8, split off the old-code removal (AC7) |

## Ticket Tree

```
Epic: SQLite storage  (total: 5 points)
└── STORY-01: Store workspace data in SQLite with Alembic migrations  (5 pts, High, depends on: —)
```
