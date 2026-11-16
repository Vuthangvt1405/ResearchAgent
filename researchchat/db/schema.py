"""Table definitions (SQLAlchemy Core), also read by Alembic autogenerate.

Every table has an integer `pk` that only the storage functions use; the
readable `slug` is what the rest of the app knows (plan D2). No I/O here.

Plan: docs/plans/sqlite-alembic-storage-plan.md §3.3
"""

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    false,
)

# SQLite can't ALTER constraints in place; Alembic's batch mode needs every one named.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

PROJECT_NAME_MAX = 80  # same rule as store.PROJECT_NAME_MAX
SOURCES = ("huggingface", "zenodo")
STORED_STATUSES = ("queued", "downloading", "ready", "failed")  # "missing" is computed, never stored
ORIGINS = ("downloaded", "created")  # PCD-1: catalog download, or a file the project's own code wrote
CREATED_PATH_MAX = 1024  # same limit as datasets_store.PATH_MAX
# A row is wholly one kind: a download linked to a pool entry, or a created file with its path and stat (PCD-1 §3.3)
ORIGIN_SHAPE = (
    "(origin = 'downloaded' AND pool_entry_pk IS NOT NULL AND path IS NULL)"
    " OR (origin = 'created' AND pool_entry_pk IS NULL AND path IS NOT NULL"
    f" AND size_bytes IS NOT NULL AND mtime_ns IS NOT NULL AND length(path) BETWEEN 1 AND {CREATED_PATH_MAX})"
)

metadata = MetaData(naming_convention=NAMING_CONVENTION)

projects = Table(
    "projects",
    metadata,
    Column("pk", Integer, primary_key=True),
    Column("slug", Text, nullable=False, unique=True),  # the project id and folder name
    Column("name", Text, nullable=False),  # display name
    Column("created_at", Text, nullable=False),  # ISO 8601 UTC text (A9)
    CheckConstraint(f"length(name) BETWEEN 1 AND {PROJECT_NAME_MAX}", name="name_length"),
)

pool_entries = Table(
    "pool_entries",
    metadata,
    Column("pk", Integer, primary_key=True),
    Column("slug", Text, nullable=False, unique=True),  # "<dataset-slug>@<rev7>": the pool folder name
    Column("source", Text, nullable=False),  # which catalog
    Column("source_id", Text, nullable=False),  # stable key in that catalog
    Column("revision", Text, nullable=True),  # HF commit hash; NULL for Zenodo
    Column("name", Text, nullable=False),  # title for people
    Column("url", Text, nullable=True),  # landing page
    Column("license", Text, nullable=True),
    Column("created_at", Text, nullable=False, server_default=""),  # newest-first order in find_entries
    CheckConstraint(f"source IN {SOURCES}", name="source_known"),
    Index(None, "source", "source_id"),  # find_entries, on every dataset request
)

pool_files = Table(
    "pool_files",
    metadata,
    Column("pk", Integer, primary_key=True),
    Column("entry_pk", Integer, ForeignKey("pool_entries.pk", ondelete="CASCADE"), nullable=False),
    Column("path", Text, nullable=False),  # relative to the entry folder
    Column("position", Integer, nullable=False),  # order of PoolEntry.files
    Column("size", BigInteger, nullable=False),  # bytes, as the catalog declared it
    Column("checksum", Text, nullable=True),  # "md5:…" / "sha256:…"
    Column("ready", Boolean, nullable=False, server_default=false()),  # verified and in the pool
    Column("mtime_ns", BigInteger, nullable=True),  # ≈1.8e18: needs 64 bits (SEC16 of NB-4)
    UniqueConstraint("entry_pk", "path"),
)

project_datasets = Table(
    "project_datasets",
    metadata,
    Column("pk", Integer, primary_key=True),
    Column("project_pk", Integer, ForeignKey("projects.pk", ondelete="CASCADE"), nullable=False),
    Column("slug", Text, nullable=False),  # the dataset id; folder under files/datasets/
    # RESTRICT: a pool entry a project still uses can never be deleted (SEC4); NULL for created files (PCD-1)
    Column("pool_entry_pk", Integer, ForeignKey("pool_entries.pk", ondelete="RESTRICT"), nullable=True),
    Column("position", Integer, nullable=False),  # order of the project's dataset list
    Column("selection", JSON, nullable=True),  # file patterns asked for; None = all files, [] stays []
    Column("status", Text, nullable=False),
    Column("requested_at", Text, nullable=False, server_default=""),  # queue order
    Column("linked_at", Text, nullable=True),
    Column("error", Text, nullable=True),  # one-line reason when failed
    Column("origin", Text, nullable=False, server_default="downloaded"),  # PCD-1: which kind of row
    Column("path", Text, nullable=True),  # created only: relative to files/ (kernel: /work/<path>)
    Column("size_bytes", BigInteger, nullable=True),  # created only: size at the last scan
    Column("mtime_ns", BigInteger, nullable=True),  # created only: spots a re-save without reading the file
    Column("inode", BigInteger, nullable=True),  # created only: a rename keeps it (rename match, AC12)
    UniqueConstraint("project_pk", "slug"),  # unique within a project; the pool is shared (D1)
    UniqueConstraint("project_pk", "path"),  # one created card per path (AC4); NULLs (downloads) don't clash
    CheckConstraint(f"status IN {STORED_STATUSES}", name="status_known"),
    CheckConstraint(f"origin IN {ORIGINS}", name="origin_known"),
    CheckConstraint(ORIGIN_SHAPE, name="origin_shape"),
    Index(None, "pool_entry_pk"),  # projects_using / "used by" counts, and the RESTRICT check
)

project_dataset_files = Table(
    "project_dataset_files",
    metadata,
    Column("pk", Integer, primary_key=True),
    Column("dataset_pk", Integer, ForeignKey("project_datasets.pk", ondelete="CASCADE"), nullable=False),
    Column("position", Integer, nullable=False),  # order of ProjectDataset.files
    Column("path", Text, nullable=False),  # no FK to pool_files: a project may list files the pool lacks
    UniqueConstraint("dataset_pk", "position"),
    UniqueConstraint("dataset_pk", "path"),
)
