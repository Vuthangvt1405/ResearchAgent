"""Open a workspace's database: create it, set the connection PRAGMAs, upgrade it to head.

`database_for(root)` is the one way in. It caches one Engine per workspace
root, so the ~60 existing `root=` call sites and every tmp_path test get their
own database without passing an Engine around (plan A2).

Plan: docs/plans/sqlite-alembic-storage-plan.md §3.3, §4.1, §6
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine, create_engine, event, text
from sqlalchemy.exc import DatabaseError

from researchchat.config import DATABASE_FILE, WORKSPACES_DIR

BUSY_TIMEOUT_MILLISECONDS = 5000
CONNECTION_PRAGMAS = ("foreign_keys=ON", "journal_mode=WAL", f"busy_timeout={BUSY_TIMEOUT_MILLISECONDS}")
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

_engines: dict[Path, Engine] = {}
_engines_lock = threading.Lock()  # download jobs may open a workspace from a worker thread


class DatabaseUnusable(SystemExit):
    """The database file can't be used: damaged, or made by a newer app (AC4).

    A SystemExit, like config.check_setup: at startup it stops the app with
    `message` (what happened and what to do) instead of a stack trace.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def database_path(root: Path = WORKSPACES_DIR) -> Path:
    """<root>/researchchat.db (name from config.toml [notebook] database_file)."""
    return Path(root) / DATABASE_FILE


def database_for(root: Path = WORKSPACES_DIR) -> Engine:
    """The Engine for this workspace root, opened, checked and upgraded on first use, then cached."""
    key = Path(root).resolve()
    with _engines_lock:
        if key not in _engines:
            _engines[key] = open_database(database_path(key))
        return _engines[key]


def open_database(database_file: Path) -> Engine:
    """Create the file if needed, refuse a damaged or newer one, bring it to head."""
    database_file.parent.mkdir(parents=True, exist_ok=True)
    engine = create_workspace_engine(database_file)
    try:
        check_database_readable(engine)
        upgrade_to_latest(engine)
    except BaseException:
        engine.dispose()
        raise
    return engine


def close_database(root: Path = WORKSPACES_DIR) -> None:
    """Forget the cached Engine for this root (tests use it to simulate a restart)."""
    with _engines_lock:
        engine = _engines.pop(Path(root).resolve(), None)
    if engine is not None:
        engine.dispose()


def close_all_databases() -> None:
    """Forget every cached Engine (tests: each tmp_path workspace is closed after its test)."""
    with _engines_lock:
        engines = list(_engines.values())
        _engines.clear()
    for engine in engines:
        engine.dispose()


def create_workspace_engine(database_file: Path) -> Engine:
    """An Engine for one SQLite file; every new connection gets CONNECTION_PRAGMAS."""
    engine = create_engine(f"sqlite:///{database_file}")
    event.listen(engine, "connect", _apply_pragmas)
    return engine


def _apply_pragmas(dbapi_connection, _connection_record) -> None:
    # foreign_keys is off by default and per connection in SQLite: without this the FKs do nothing
    cursor = dbapi_connection.cursor()
    try:
        for pragma in CONNECTION_PRAGMAS:
            cursor.execute(f"PRAGMA {pragma}")
    finally:
        cursor.close()


def check_database_readable(engine: Engine) -> None:
    """Raise DatabaseUnusable when the file isn't a SQLite database."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT count(*) FROM sqlite_master"))
    except DatabaseError as error:
        raise DatabaseUnusable(
            f"{engine.url.database} is damaged or isn't a ResearchChat database ({error.orig}). "
            "Move it away to start with an empty workspace."
        ) from error


def upgrade_to_latest(engine: Engine) -> None:
    """Run Alembic `upgrade head` on this engine; refuse a revision this code doesn't know."""
    config = alembic_config()
    with engine.connect() as connection, foreign_keys_off(connection), connection.begin():
        refuse_unknown_revision(connection, ScriptDirectory.from_config(config), str(engine.url.database))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        refuse_broken_foreign_keys(connection, str(engine.url.database))


@contextmanager
def foreign_keys_off(connection: Connection) -> Iterator[None]:
    """Foreign keys off while migrations run, back on after.

    Batch migrations drop and recreate a table; with foreign keys on, that DROP
    cascades into child tables (0002 would empty project_dataset_files). SQLite
    ignores this PRAGMA inside a transaction, so it is set before Alembic's.
    """
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    connection.commit()
    try:
        yield
    finally:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()


def refuse_broken_foreign_keys(connection: Connection, database_name: str) -> None:
    """Roll the upgrade back when a migration left a row pointing at nothing."""
    broken_references = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
    if broken_references:
        raise DatabaseUnusable(
            f"Upgrading {database_name} would break {len(broken_references)} links between rows, "
            "so it was not changed. Please report this, with the app log."
        )


def alembic_config() -> Config:
    """The same migrations the alembic CLI uses, without reading alembic.ini (the app keeps its logging)."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


def refuse_unknown_revision(connection: Connection, scripts: ScriptDirectory, database_name: str) -> None:
    current_revisions = MigrationContext.configure(connection).get_current_heads()
    known_revisions = {script.revision for script in scripts.walk_revisions()}
    unknown_revisions = [revision for revision in current_revisions if revision not in known_revisions]
    if unknown_revisions:
        raise DatabaseUnusable(
            f"{database_name} was made by a newer ResearchChat (schema {', '.join(unknown_revisions)}, "
            f"this version knows up to {scripts.get_current_head()}). "
            "Update the app, or move the file away to start fresh."
        )
