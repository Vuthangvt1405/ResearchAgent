"""Created datasets: project_datasets rows for data files the project's own code wrote.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-16

Foreign keys: batch mode drops and recreates project_datasets, which would
cascade-delete every project_dataset_files row with foreign keys on.
engine.upgrade_to_latest runs every migration with them off and checks them
afterwards.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A row is wholly one kind: a catalog download linked to a pool entry, or a file the project's code wrote.
ORIGIN_SHAPE = (
    "(origin = 'downloaded' AND pool_entry_pk IS NOT NULL AND path IS NULL)"
    " OR (origin = 'created' AND pool_entry_pk IS NULL AND path IS NOT NULL"
    " AND size_bytes IS NOT NULL AND mtime_ns IS NOT NULL AND length(path) BETWEEN 1 AND 1024)"
)


def upgrade() -> None:
    # SQLite can't change nullability in place; batch mode rebuilds the table (named constraints survive).
    with op.batch_alter_table("project_datasets") as batch:
        batch.alter_column("pool_entry_pk", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("origin", sa.Text(), server_default="downloaded", nullable=False))
        batch.add_column(sa.Column("path", sa.Text(), nullable=True))
        batch.add_column(sa.Column("size_bytes", sa.BigInteger(), nullable=True))
        batch.add_column(sa.Column("mtime_ns", sa.BigInteger(), nullable=True))
        batch.add_column(sa.Column("inode", sa.BigInteger(), nullable=True))
        batch.create_check_constraint(op.f("ck_project_datasets_origin_known"), "origin IN ('downloaded', 'created')")
        batch.create_check_constraint(op.f("ck_project_datasets_origin_shape"), ORIGIN_SHAPE)
        batch.create_unique_constraint(op.f("uq_project_datasets_project_pk_path"), ["project_pk", "path"])


def downgrade() -> None:
    # Created rows can't exist without a pool entry in 0001; their files stay on disk.
    op.execute("DELETE FROM project_datasets WHERE origin = 'created'")
    with op.batch_alter_table("project_datasets") as batch:
        batch.drop_constraint(op.f("uq_project_datasets_project_pk_path"), type_="unique")
        batch.drop_constraint(op.f("ck_project_datasets_origin_shape"), type_="check")
        batch.drop_constraint(op.f("ck_project_datasets_origin_known"), type_="check")
        batch.drop_column("inode")
        batch.drop_column("mtime_ns")
        batch.drop_column("size_bytes")
        batch.drop_column("path")
        batch.drop_column("origin")
        batch.alter_column("pool_entry_pk", existing_type=sa.Integer(), nullable=False)
