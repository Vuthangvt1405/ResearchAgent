"""Alembic environment: the app passes its open connection; the CLI opens config.toml's database.

Plan: docs/plans/sqlite-alembic-storage-plan.md §4.1
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, create_engine, pool

from researchchat.db.engine import database_path
from researchchat.db.schema import metadata

config = context.config
app_connection: Connection | None = config.attributes.get("connection")


def run_migrations(connection: Connection) -> None:
    # SQLite can't ALTER most things; batch mode copies the table instead
    context.configure(connection=connection, target_metadata=metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_from_cli() -> None:
    """`alembic upgrade head` from the repo root: the workspace database from config.toml,
    or another file with `alembic -x database=path/to/file.db upgrade head`."""
    if config.config_file_name:
        fileConfig(config.config_file_name)  # only for the CLI: the app keeps its own logging
    database_file = context.get_x_argument(as_dictionary=True).get("database") or database_path()
    engine = create_engine(f"sqlite:///{database_file}", poolclass=pool.NullPool)
    with engine.connect() as connection:
        run_migrations(connection)


if context.is_offline_mode():
    raise SystemExit("Offline (--sql) migrations aren't supported; run them against the database.")
if app_connection is not None:
    run_migrations(app_connection)
else:
    run_from_cli()
