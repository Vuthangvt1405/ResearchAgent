"""Initial schema: projects, project datasets and the shared pool index.

Revision ID: 0001
Revises:
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("pk", sa.Integer(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint("length(name) BETWEEN 1 AND 80", name=op.f("ck_projects_name_length")),
        sa.PrimaryKeyConstraint("pk", name=op.f("pk_projects")),
        sa.UniqueConstraint("slug", name=op.f("uq_projects_slug")),
    )
    op.create_table(
        "pool_entries",
        sa.Column("pk", sa.Integer(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("revision", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("license", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), server_default="", nullable=False),
        sa.CheckConstraint("source IN ('huggingface', 'zenodo')", name=op.f("ck_pool_entries_source_known")),
        sa.PrimaryKeyConstraint("pk", name=op.f("pk_pool_entries")),
        sa.UniqueConstraint("slug", name=op.f("uq_pool_entries_slug")),
    )
    op.create_index(op.f("ix_pool_entries_source_source_id"), "pool_entries", ["source", "source_id"])
    op.create_table(
        "pool_files",
        sa.Column("pk", sa.Integer(), nullable=False),
        sa.Column("entry_pk", sa.Integer(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=True),
        sa.Column("ready", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("mtime_ns", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["entry_pk"], ["pool_entries.pk"], name=op.f("fk_pool_files_entry_pk_pool_entries"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("pk", name=op.f("pk_pool_files")),
        sa.UniqueConstraint("entry_pk", "path", name=op.f("uq_pool_files_entry_pk_path")),
    )
    op.create_table(
        "project_datasets",
        sa.Column("pk", sa.Integer(), nullable=False),
        sa.Column("project_pk", sa.Integer(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("pool_entry_pk", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("selection", sa.JSON(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("requested_at", sa.Text(), server_default="", nullable=False),
        sa.Column("linked_at", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'downloading', 'ready', 'failed')", name=op.f("ck_project_datasets_status_known")
        ),
        sa.ForeignKeyConstraint(
            ["pool_entry_pk"], ["pool_entries.pk"],
            name=op.f("fk_project_datasets_pool_entry_pk_pool_entries"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_pk"], ["projects.pk"], name=op.f("fk_project_datasets_project_pk_projects"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("pk", name=op.f("pk_project_datasets")),
        sa.UniqueConstraint("project_pk", "slug", name=op.f("uq_project_datasets_project_pk_slug")),
    )
    op.create_index(op.f("ix_project_datasets_pool_entry_pk"), "project_datasets", ["pool_entry_pk"])
    op.create_table(
        "project_dataset_files",
        sa.Column("pk", sa.Integer(), nullable=False),
        sa.Column("dataset_pk", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_pk"], ["project_datasets.pk"],
            name=op.f("fk_project_dataset_files_dataset_pk_project_datasets"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("pk", name=op.f("pk_project_dataset_files")),
        sa.UniqueConstraint("dataset_pk", "path", name=op.f("uq_project_dataset_files_dataset_pk_path")),
        sa.UniqueConstraint("dataset_pk", "position", name=op.f("uq_project_dataset_files_dataset_pk_position")),
    )


def downgrade() -> None:
    op.drop_table("project_dataset_files")
    op.drop_index(op.f("ix_project_datasets_pool_entry_pk"), table_name="project_datasets")
    op.drop_table("project_datasets")
    op.drop_table("pool_files")
    op.drop_index(op.f("ix_pool_entries_source_source_id"), table_name="pool_entries")
    op.drop_table("pool_entries")
    op.drop_table("projects")
