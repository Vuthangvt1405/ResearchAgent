"""SQLite database: schema, Alembic migrations, placement and injection.
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
from researchchat.workspace import store
from researchchat.workspace.datasets import store as ds
from researchchat.workspace.datasets.pool import DatasetPool, PoolEntry, PoolFile
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


# ---- Schema and migrations · integration
# Baseline: Given an empty `tmp_path/workspaces` · When `database_for(root)` is called


def test_first_open_creates_database_at_head(root):
    # baseline
    # Changed: —
    # Then: researchchat.db exists; alembic_version = head; all five tables exist
    # Demonstrates: a fresh workspace gets the full schema with no manual step
    engine = db.database_for(root)

    assert db.database_path(root).is_file()
    assert current_revisions(engine) == ("0002",)
    assert APP_TABLES <= table_names(engine)


def test_second_open_reuses_database_without_migrating(root):
    # edge
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
    assert current_revisions(second) == ("0002",)
    with second.connect() as connection:
        assert connection.execute(text("SELECT slug FROM projects")).scalars().all() == ["p1"]


def test_migrations_match_table_definitions(root):
    # edge
    # Changed: compare upgrade head with schema.metadata (Alembic compare_metadata)
    # Then: no differences
    # Demonstrates: the migration and the code can't drift
    engine = db.database_for(root)

    with engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), metadata)

    assert differences == []


def test_downgrade_to_base_removes_all_tables(root):
    # edge
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
    # negative
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
    # negative
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
    # negative
    # Changed: researchchat.db contains random bytes
    # Then: SystemExit with the "damaged" text; file bytes unchanged
    # Demonstrates: a broken file gives steps, not a stack trace
    root.mkdir(parents=True)
    garbage = os.urandom(4096)
    db.database_path(root).write_bytes(garbage)

    with pytest.raises(SystemExit, match="damaged"):
        db.database_for(root)

    assert db.database_path(root).read_bytes() == garbage


# ---- Database placement and injection · unit / integration
# Baseline: Given a workspace at head


def test_database_file_is_outside_kernel_mounts(root):
    # negative
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
    # negative
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


# ---- Storage: both kinds in one table · integration (real SQLite)
# Baseline: Given a workspace with project `p` and a downloaded dataset `hf-x` (pool entry + 2 file rows) ·
#   When migration 0002 runs up or down


def migrate(engine, step, revision: str) -> None:
    """Run one Alembic step the way the app does: foreign keys off around the transaction."""
    config = db.alembic_config()
    with engine.connect() as connection, db.foreign_keys_off(connection), connection.begin():
        config.attributes["connection"] = connection
        step(config, revision)


def seed_downloaded_dataset(engine) -> None:
    """Project p with dataset hf-x (pool entry hf-x@1) listing a.csv and b.csv."""
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO projects (slug, name, created_at) VALUES ('p', 'P', 't')"))
        connection.execute(text(
            "INSERT INTO pool_entries (slug, source, source_id, name, created_at) "
            "VALUES ('hf-x@1', 'huggingface', 'o/x', 'X', 't')"
        ))
        connection.execute(text(
            "INSERT INTO project_datasets (project_pk, slug, pool_entry_pk, position, status) VALUES (1, 'hf-x', 1, 0, 'ready')"
        ))
        connection.execute(text(
            "INSERT INTO project_dataset_files (dataset_pk, position, path) VALUES (1, 0, 'a.csv'), (1, 1, 'b.csv')"
        ))


def insert_created_row(engine) -> None:
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO project_datasets (project_pk, slug, position, status, origin, path, size_bytes, mtime_ns, inode) "
            "VALUES (1, 'file-iris-csv', 1, 'ready', 'created', 'Iris.csv', 4551, 1, 7)"
        ))


def file_list_paths(engine) -> list[str]:
    with engine.connect() as connection:
        return list(connection.execute(text("SELECT path FROM project_dataset_files ORDER BY position")).scalars())


def test_migration_0002_marks_existing_rows_downloaded(root):
    # edge
    # Changed: upgrade a 0001 database with rows
    # Then: every old row `origin = 'downloaded'`, pool entry kept, `status_known` check still there,
    #   and every `project_dataset_files` row intact (the rebuild must not cascade-delete them)
    # Demonstrates: upgrade loses nothing
    engine = db.database_for(root)
    migrate(engine, command.downgrade, "0001")
    seed_downloaded_dataset(engine)

    migrate(engine, command.upgrade, "head")

    with engine.connect() as connection:
        row = connection.execute(text("SELECT origin, pool_entry_pk, path FROM project_datasets")).one()
    assert tuple(row) == ("downloaded", 1, None)
    assert file_list_paths(engine) == ["a.csv", "b.csv"]
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text("UPDATE project_datasets SET status = 'missing'"))


def test_migration_0002_downgrade_drops_created_rows_only(root):
    # edge
    # Changed: downgrade to 0001
    # Then: created rows gone, downloaded rows and their `project_dataset_files` intact,
    #   `pool_entry_pk` NOT NULL again; files on disk untouched
    # Demonstrates: rollback is safe
    engine = db.database_for(root)
    seed_downloaded_dataset(engine)
    insert_created_row(engine)
    created_file = root / "p" / "files" / "Iris.csv"
    created_file.parent.mkdir(parents=True)
    created_file.write_text("a,b\n")

    migrate(engine, command.downgrade, "0001")

    with engine.connect() as connection:
        assert list(connection.execute(text("SELECT slug FROM project_datasets")).scalars()) == ["hf-x"]
    assert file_list_paths(engine) == ["a.csv", "b.csv"]
    columns = {column["name"]: column for column in inspect(engine).get_columns("project_datasets")}
    assert columns["pool_entry_pk"]["nullable"] is False and "origin" not in columns
    assert created_file.read_text() == "a,b\n"


def test_upgrade_with_foreign_keys_on_would_empty_file_lists(root):
    # proves why engine.foreign_keys_off exists
    # Changed: the same upgrade, but run inside one transaction with foreign keys on
    # Then: project_dataset_files is emptied by the table rebuild's DROP
    # Demonstrates: the guard in upgrade_to_latest is load-bearing
    engine = db.database_for(root)
    migrate(engine, command.downgrade, "0001")
    seed_downloaded_dataset(engine)
    config = db.alembic_config()

    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

    assert file_list_paths(engine) == []
