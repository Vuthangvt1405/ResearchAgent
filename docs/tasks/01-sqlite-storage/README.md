# Sprint Backlog — SQLite storage

[Epic PRD](../../requirements/01-sqlite-storage/README.md)

| # | Story | Points | Priority | Depends on | Status |
|---|---|---|---|---|---|
| 1 | [STORY-01: Store workspace data in SQLite with Alembic migrations](STORY-01-store-app-data-in-sqlite.md) | 5 | High | — | Ready |

Total: 5 points.

## Later sprints

Not ready yet and not in this sprint. Turn into a story (with `jira-story-writer`) when it's picked up.

| Item | Why it's here | Raised in |
|---|---|---|
| Row-by-row database updates in the dataset services | STORY-01 keeps the "load the whole list, change it, save it" style so behaviour stays identical; saving single rows is simpler and cheaper once the database is in | [plan, A4](../../plans/sqlite-alembic-storage-plan.md) |
| Update the "explained" docs for the workspace package | `docs/explained/workspace-package-explained.md` and `project-workspace-explained.md` still describe the JSON files | [plan, §8 follow-ups](../../plans/sqlite-alembic-storage-plan.md) |
