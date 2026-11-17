"""Link source: pool entries may come from a file link the user pasted.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-17

Only widens the source check of pool_entries. Batch mode drops and recreates
pool_entries, which pool_files (CASCADE) and project_datasets (RESTRICT)
point at; engine.upgrade_to_latest runs every migration with foreign keys off
and checks them afterwards.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCES_BEFORE = "source IN ('huggingface', 'zenodo')"
SOURCES_AFTER = "source IN ('huggingface', 'zenodo', 'link')"


def upgrade() -> None:
    with op.batch_alter_table("pool_entries") as batch:
        batch.drop_constraint(op.f("ck_pool_entries_source_known"), type_="check")
        batch.create_check_constraint(op.f("ck_pool_entries_source_known"), SOURCES_AFTER)


def downgrade() -> None:
    # Dropping link entries would orphan the projects using them, so a downgrade stops instead.
    link_entries = op.get_bind().execute(sa.text("SELECT count(*) FROM pool_entries WHERE source = 'link'")).scalar()
    if link_entries:
        raise RuntimeError(f"{link_entries} pool entries come from pasted links; delete those datasets before downgrading.")
    with op.batch_alter_table("pool_entries") as batch:
        batch.drop_constraint(op.f("ck_pool_entries_source_known"), type_="check")
        batch.create_check_constraint(op.f("ck_pool_entries_source_known"), SOURCES_BEFORE)
