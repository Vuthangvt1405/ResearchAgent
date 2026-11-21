"""The app's own database: one SQLite file per workspace root.

workspaces/
    sillytherin.db        projects, project datasets, the shared pool index
    sillytherin.db-wal    WAL sidecar files (SQLite)
    sillytherin.db-shm

Kernels never see this file: they only get files/, .kernels and .dataset-pool
mounted (kernels.py), so notebook code can't edit app data. Alembic owns the
schema (schema.py + migrations/); notebooks, project files and pooled bytes
stay files on disk.
"""
