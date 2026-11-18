"""Dataset descriptions: what each dataset is about, so the assistant can match by meaning.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-18

Adds four nullable columns; existing rows keep NULL and nothing else changes:
- pool_entries.description: the catalog's one-line description
- project_datasets.columns: created files' column names (NULL = not read yet)
- project_datasets.assistant_description: one line the assistant wrote
- project_datasets.created_by: who added a created file: "assistant" / "user" (a cell run by
  either) or "upload" (appeared with no run); NULL (from before) counts as an upload

The upgrade only adds columns (SQLite ADD COLUMN, with the created_by check
on the column), so no table is rebuilt. The downgrade uses batch mode, which
recreates both tables; engine.upgrade_to_latest runs every migration with
foreign keys off and checks them afterwards.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CREATED_BY_KNOWN = "created_by IS NULL OR created_by IN ('assistant', 'user', 'upload')"


def upgrade() -> None:
    # Plain ADD COLUMN, no table rebuild: the existing tables and the order of their checks stay as they are.
    op.add_column("pool_entries", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("project_datasets", sa.Column("columns", sa.JSON(), nullable=True))
    op.add_column("project_datasets", sa.Column("assistant_description", sa.Text(), nullable=True))
    op.execute(
        "ALTER TABLE project_datasets ADD COLUMN created_by TEXT"
        f" CONSTRAINT ck_project_datasets_created_by_known CHECK ({CREATED_BY_KNOWN})"
    )


def downgrade() -> None:
    # Only these four columns go; assistant-written descriptions are lost, nothing else.
    with op.batch_alter_table("project_datasets") as batch:
        batch.drop_constraint(op.f("ck_project_datasets_created_by_known"), type_="check")
        batch.drop_column("created_by")
        batch.drop_column("assistant_description")
        batch.drop_column("columns")
    with op.batch_alter_table("pool_entries") as batch:
        batch.drop_column("description")
