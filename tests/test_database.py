"""SQLite database: schema, Alembic migrations, placement and injection (SQLite plan G1, S1).

Plan: docs/plans/sqlite-alembic-storage-plan.md §7
"""

import os
import sqlite3

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from researchchat.db import engine as db
from researchchat.db.schema import metadata
from researchchat.workspace import datasets_store as ds
from researchchat.workspace import store
from researchchat.workspace.dataset_pool import DatasetPool, PoolEntry, PoolFile
from researchchat.workspace.kernels import ContainerMounts, KernelRegistry

APP_TABLES = {"projects", "pool_entries", "pool_files", "project_datasets", "project_dataset_files"}
UNKNOWN_REVISION = "9999"


@pytest.fixture
def root(tmp_path):
    """An empty workspaces_dir; its cached Engine is dropped afterwards."""
    workspace_root = tmp_path / "workspaces"
    yield workspace_root
    db.close_database(workspace_root)


def current_revisions(engine) -> tuple[str, ...]:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_heads()


def table_names(engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def stored_revision(database_file) -> str:
    """Read alembic_version with plain sqlite3, outside the app's engine."""
    with sqlite3.connect(database_file) as connection:
        return connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]


# ---- SQLite plan G1 — Schema and migrations (AC1, AC4, AC5, SEC4, SEC6) · integration
# Baseline: Given an empty `tmp_path/workspaces` · When `database_for(root)` is called


def test_first_open_creates_database_at_head(root):
    # G1✅1 · baseline
    # Changed: —
    # Then: researchchat.db exists; alembic_version = head; all five tables exist
    # Demonstrates: a fresh workspace gets the full schema with no manual step
    engine = db.database_for(root)

    assert db.database_path(root).is_file()
    assert current_revisions(engine) == ("0001",)
    assert APP_TABLES <= table_names(engine)


def test_second_open_reuses_database_without_migrating(root):
    # G1✅2 · edge
    # Changed: called twice (and on a second Engine)
    # Then: same file; no revision applied the second time; rows kept
    # Demonstrates: upgrading at every start is safe
    first = db.database_for(root)
    assert db.database_for(root) is first
    with first.begin() as connection:
        connection.execute(text("INSERT INTO projects (slug, name, created_at) VALUES ('p1', 'P1', 't')"))

    db.close_database(root)
    second = db.database_for(root)

    assert second is not first
    assert current_revisions(second) == ("0001",)
    with second.connect() as connection:
        assert connection.execute(text("SELECT slug FROM projects")).scalars().all() == ["p1"]


def test_migrations_match_table_definitions(root):
    # G1✅3 · edge
    # Changed: compare upgrade head with schema.metadata (Alembic compare_metadata)
    # Then: no differences
    # Demonstrates: the migration and the code can't drift (AC5)
    engine = db.database_for(root)

    with engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), metadata)

    assert differences == []


def test_downgrade_to_base_removes_all_tables(root):
    # G1✅4 · edge
    # Changed: downgrade base after upgrade
    # Then: no app tables left
    # Demonstrates: the rollback path works
    engine = db.database_for(root)
    config = db.alembic_config()

    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "base")

    assert table_names(engine) & APP_TABLES == set()


def test_foreign_keys_are_enforced_on_every_connection(root):
    # G1❌1 · negative
    # Changed: insert a project_datasets row whose pool_entry_pk doesn't exist, on a fresh pooled connection
    # Then: IntegrityError; no row
    # Demonstrates: the FK actually holds (the PRAGMA isn't forgotten)
    db.database_for(root)
    fresh_engine = db.create_workspace_engine(db.database_path(root))
    try:
        with pytest.raises(IntegrityError), fresh_engine.begin() as connection:
            connection.execute(text("INSERT INTO projects (slug, name, created_at) VALUES ('p1', 'P1', 't')"))
            connection.execute(text(
                "INSERT INTO project_datasets (project_pk, slug, pool_entry_pk, position, status) "
                "VALUES (1, 'd', 999, 0, 'ready')"
            ))
        with fresh_engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM project_datasets")).scalar() == 0
    finally:
        fresh_engine.dispose()


def test_database_from_newer_version_stops_startup(root):
    # G1❌2 · negative
    # Changed: alembic_version set to "9999"
    # Then: SystemExit with the "newer version" text; file bytes unchanged
    # Demonstrates: the app never writes to a schema it doesn't know
    engine = db.database_for(root)
    with engine.begin() as connection:
        connection.execute(text(f"UPDATE alembic_version SET version_num = '{UNKNOWN_REVISION}'"))
    db.close_database(root)

    with pytest.raises(SystemExit, match="newer ResearchChat") as stopped:
        db.database_for(root)

    assert isinstance(stopped.value, db.DatabaseUnusable)
    assert stored_revision(db.database_path(root)) == UNKNOWN_REVISION


def test_unreadable_database_file_stops_startup(root):
    # G1❌3 · negative
    # Changed: researchchat.db contains random bytes
    # Then: SystemExit with the "damaged" text; file bytes unchanged
    # Demonstrates: a broken file gives steps, not a stack trace
    root.mkdir(parents=True)
    garbage = os.urandom(4096)
    db.database_path(root).write_bytes(garbage)

    with pytest.raises(SystemExit, match="damaged"):
        db.database_for(root)

    assert db.database_path(root).read_bytes() == garbage


# ---- SQLite plan S1 — Database placement and injection (SEC1, SEC2) · unit / integration
# Baseline: Given a workspace at head


def test_database_file_is_outside_kernel_mounts(root):
    # S1❌1 · negative
    # Changed: KernelRegistry.run_arguments(...) for a project
    # Then: no mount source is, or contains, researchchat.db or the workspaces/ root
    # Demonstrates: kernel code can't edit app data
    mounts = ContainerMounts(root / "p1" / "files", root / ".kernels" / "p1", root / ".dataset-pool")
    arguments = KernelRegistry().run_arguments("rc-kernel-x", "p1", mounts, (1, 2, 3, 4, 5))
    sources = [
        arguments[i + 1].split("source=")[1].split(",")[0] for i, a in enumerate(arguments) if a == "--mount"
    ]
    database_file = db.database_path(root)

    assert sources and str(root) not in sources
    assert not any(database_file.is_relative_to(source) for source in sources)


def test_sql_metacharacters_are_stored_as_plain_text(root):
    # S1❌2 · negative
    # Changed: project name `x'); DROP TABLE projects; --`, file path `a'b.csv`, license `"; --`
    # Then: stored and read back verbatim; all tables still exist
    # Demonstrates: values never become SQL
    hostile_name, hostile_path, hostile_license = "x'); DROP TABLE projects; --", "a'b.csv", '"; --'
    project = store.create_project(hostile_name, root)
    pool = DatasetPool(root)
    pool.add_entry(PoolEntry("zenodo-1", "zenodo", "1", None, hostile_name, None, hostile_license,
                             [PoolFile(hostile_path, 1, None, True)]))
    pool.save_index()
    ds.save_project_datasets(project.id, [ds.ProjectDataset("zenodo-1", "zenodo-1", [hostile_path], "ready", [hostile_path])], root)

    assert store.get_project(project.id, root).name == hostile_name
    entry = DatasetPool(root).get_entry("zenodo-1")
    assert (entry.license, entry.files[0].path) == (hostile_license, hostile_path)
    assert ds.load_project_datasets(project.id, root)[0].files == [hostile_path]
    assert APP_TABLES <= table_names(db.database_for(root))
