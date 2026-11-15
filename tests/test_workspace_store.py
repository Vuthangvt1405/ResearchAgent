"""Projects and notebook files on disk.

Plan: docs/plans/done/notebook-workspace-plan.md section 7.
"""

from pathlib import Path

import nbformat
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from researchchat.db.engine import database_for
from researchchat.workspace import ErrorCode, WorkspaceError
from researchchat.workspace import store


@pytest.fixture
def root(tmp_path):
    """An empty workspaces_dir."""
    return tmp_path / "workspaces"


class FakeSession:
    """Stands in for cl.user_session."""

    def __init__(self, **values):
        self.values = dict(values)

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


# ---- Group 1: Projects (AC1, AC5, AC18) · unit
# Baseline: Given an empty temp `workspaces_dir` · When a project "Tokyo housing" is created and its notebook is loaded


def test_project_name_becomes_safe_slug():
    # G1✅2 (edge) · Demonstrates: any name works, folder names stay safe
    assert store.slugify("Tokyo Housing!!") == "tokyo-housing"
    assert store.slugify("  Nhà ở Tokyo  ") == "nha-o-tokyo"
    assert store.slugify("東京") == "project"  # nothing Latin left
    assert store.PROJECT_ID_RE.match(store.slugify("x" * 200))


def test_default_project_created_on_first_start(root):
    # G1✅3 (edge) · Demonstrates: the app is usable right away
    project = store.ensure_default_project(root)
    assert project.id == store.DEFAULT_PROJECT_ID
    assert [p.id for p in store.list_projects(root)] == ["default"]
    # A second start doesn't create another one
    store.ensure_default_project(root)
    assert len(store.list_projects(root)) == 1


def test_notebook_round_trips_cells_and_outputs(root):
    # G1✅4 (edge) · Demonstrates: work survives restarts
    pid = store.create_project("Tokyo housing", root).id
    nb = store.load_notebook(pid, root)
    cell = store.add_cell(nb, "code", None)
    store.update_cell(nb, cell.id, "x = 5\nx * 2")
    cell.execution_count = 1
    cell.outputs = [nbformat.v4.new_output("execute_result", {"text/plain": "10"}, execution_count=1)]
    store.add_cell(nb, "markdown", cell.id)
    store.save_notebook(pid, nb, root)

    again = store.load_notebook(pid, root)
    assert again == nb


def test_saved_notebook_is_valid_nbformat(root):
    # G1✅5 (edge) · Demonstrates: file opens in Jupyter/VS Code
    pid = store.create_project("Tokyo housing", root).id
    nb = store.load_notebook(pid, root)
    store.add_cell(nb, "code", None)
    store.save_notebook(pid, nb, root)
    on_disk = nbformat.read(root / pid / "notebook.ipynb", as_version=4)
    nbformat.validate(on_disk)
    assert (on_disk.nbformat, on_disk.nbformat_minor) >= (4, 5)


def test_save_is_atomic_when_write_fails(root, monkeypatch):
    # G1❌1 (negative) · Demonstrates: a crash never corrupts a notebook
    pid = store.create_project("Tokyo housing", root).id
    path = root / pid / "notebook.ipynb"
    before = path.read_text("utf-8")

    def broken_write(nb, f):
        f.write('{"half": ')
        raise OSError("disk full")

    monkeypatch.setattr(store.nbformat, "write", broken_write)
    nb = store.load_notebook(pid, root)
    store.add_cell(nb, "code", None)
    with pytest.raises(OSError):
        store.save_notebook(pid, nb, root)
    assert path.read_text("utf-8") == before
    assert list((root / pid).glob("*.tmp")) == []


def test_duplicate_name_gets_unique_id(root):
    # G1❌2 (negative) · Demonstrates: projects never overwrite each other
    first = store.create_project("Tokyo housing", root)
    nb = store.load_notebook(first.id, root)
    store.add_cell(nb, "code", None)
    store.save_notebook(first.id, nb, root)

    second = store.create_project("Tokyo housing", root)
    assert second.id == "tokyo-housing-2"
    assert len(store.load_notebook(first.id, root).cells) == 1


def test_switch_project_changes_session_and_panel(root, service_factory):
    # G1✅6 (edge) · Demonstrates: the bottom bar switches projects (AC18)
    from researchchat.workspace import actions

    store.create_project("P", root)
    store.create_project("Q", root)
    service = service_factory(root)
    session = FakeSession(project_id="p")
    props = run(actions.switch_project(service, session, "q"))
    assert session.get("project_id") == "q"
    assert props["project"] == {"id": "q", "name": "Q"}


def test_create_project_from_bar_switches_to_it(root, service_factory):
    # G1✅7 (edge)
    from researchchat.workspace import actions

    store.create_project("P", root)
    service = service_factory(root)
    session = FakeSession(project_id="p")
    props = run(actions.create_and_switch(service, session, "Climate"))
    assert session.get("project_id") == "climate"
    assert props["project"]["name"] == "Climate"
    assert (root / "climate" / "notebook.ipynb").exists()


def test_switch_to_missing_project_is_rejected(root, service_factory):
    # G1❌3 (negative)
    from researchchat.workspace import actions

    store.create_project("P", root)
    service = service_factory(root)
    session = FakeSession(project_id="p")
    with pytest.raises(WorkspaceError) as err:
        run(actions.switch_project(service, session, "nope"))
    assert err.value.code == ErrorCode.NOT_FOUND
    assert session.get("project_id") == "p"


def run(coro):
    import asyncio

    return asyncio.run(coro)


# ---- SQLite plan G2 — Projects in the database (AC2, AC6, SEC3) · integration
# Baseline: Given a workspace at head · When `store.create_project("Tokyo housing", root)` and then `list_projects` / `get_project`
# Plan: docs/plans/sqlite-alembic-storage-plan.md §7


def project_rows(root) -> list[tuple[str, str]]:
    with database_for(root).connect() as connection:
        return [tuple(row) for row in connection.execute(text("SELECT slug, name FROM projects ORDER BY pk"))]


def insert_project_row(root, slug: str) -> None:
    with database_for(root).begin() as connection:
        connection.execute(
            text("INSERT INTO projects (slug, name, created_at) VALUES (:slug, 'Hand made', 't')"), {"slug": slug}
        )


def test_new_project_is_a_row_with_notebook_and_files_dir(root):
    # G2✅1 · baseline · rewrite of test_new_project_has_empty_notebook_and_files_dir
    # Changed: —
    # Then: row (slug tokyo-housing, "Tokyo housing", created_at); folder has notebook.ipynb and files/; **no** project.json
    # Demonstrates: projects live in the DB, notebooks stay files
    project = store.create_project("Tokyo housing", root)

    folder = root / project.id
    assert project.id == "tokyo-housing"
    assert project_rows(root) == [("tokyo-housing", "Tokyo housing")]
    assert store.get_project("tokyo-housing", root) == project
    assert (folder / "files").is_dir()
    assert not (folder / "project.json").exists()
    notebook = store.load_notebook(project.id, root)
    assert notebook.cells == []
    assert store.get_version(notebook) == 0


def test_projects_are_listed_by_name_then_id(root):
    # G2✅2 · edge
    # Changed: three projects, names differing only in case
    # Then: same order as today (name.lower(), then id)
    # Demonstrates: sorting didn't change
    store.create_project("beta", root, project_id="b2")
    store.create_project("Alpha", root, project_id="a1")
    store.create_project("Beta", root, project_id="b1")

    assert [p.id for p in store.list_projects(root)] == ["a1", "b1", "b2"]


@pytest.mark.parametrize("bad_name", ["", "   ", "x" * (store.PROJECT_NAME_MAX + 1)])
def test_bad_project_names_are_rejected_without_a_row(root, bad_name):
    # G2❌1 · negative
    # Changed: name "", "   ", 81 chars
    # Then: BAD_NAME; no row; no folder
    # Demonstrates: validation still runs before any write
    store.ensure_default_project(root)

    with pytest.raises(WorkspaceError) as rejected:
        store.create_project(bad_name, root)

    assert rejected.value.code == ErrorCode.BAD_NAME
    assert project_rows(root) == [("default", "Default")]
    assert sorted(p.name for p in root.iterdir() if p.is_dir()) == ["default"]


def test_failed_folder_create_leaves_no_row(root, monkeypatch):
    # G2❌2 · negative
    # Changed: mkdir raises OSError
    # Then: error raised; no row
    # Demonstrates: a project is never half-created
    store.ensure_default_project(root)
    real_mkdir = Path.mkdir

    def refuse_project_folder(self, *args, **kwargs):
        if self.name == "tokyo-housing":
            raise OSError("disk full")
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", refuse_project_folder)

    with pytest.raises(OSError, match="disk full"):
        store.create_project("Tokyo housing", root)

    assert project_rows(root) == [("default", "Default")]


def test_id_taken_by_a_folder_without_a_row_is_not_reused(root):
    # G2❌3 · negative
    # Changed: workspaces/tokyo-housing/ exists, no row
    # Then: new project gets tokyo-housing-2; old folder untouched
    # Demonstrates: a stray folder is never overwritten
    stray = root / "tokyo-housing"
    stray.mkdir(parents=True)
    (stray / "keep.txt").write_text("mine")

    project = store.create_project("Tokyo housing", root)

    assert project.id == "tokyo-housing-2"
    assert sorted(p.name for p in stray.iterdir()) == ["keep.txt"]


def test_unknown_project_is_not_found(root):
    # G2❌4 · negative
    # Changed: get_project("nope")
    # Then: NOT_FOUND
    # Demonstrates: same error as today
    store.ensure_default_project(root)

    with pytest.raises(WorkspaceError) as missing:
        store.get_project("nope", root)

    assert missing.value.code == ErrorCode.NOT_FOUND


def test_tampered_project_row_is_ignored(root, tmp_path):
    # G2❌5 · negative
    # Changed: a row with slug ../x inserted by hand
    # Then: not listed; get_project("../x") → NOT_FOUND; nothing outside root touched
    # Demonstrates: a tampered row can't become a path
    store.ensure_default_project(root)
    insert_project_row(root, "../x")
    before_outside = sorted(p.name for p in tmp_path.iterdir())

    assert [p.id for p in store.list_projects(root)] == ["default"]
    with pytest.raises(WorkspaceError) as missing:
        store.get_project("../x", root)
    assert missing.value.code == ErrorCode.NOT_FOUND
    assert sorted(p.name for p in tmp_path.iterdir()) == before_outside


def test_duplicate_project_slug_is_refused_by_the_database(root):
    # G2❌6 · negative
    # Changed: insert a second row with slug default directly
    # Then: IntegrityError (UNIQUE); one row
    # Demonstrates: the unique slug holds even when _unique_id is bypassed
    store.ensure_default_project(root)

    with pytest.raises(IntegrityError):
        insert_project_row(root, "default")

    assert project_rows(root) == [("default", "Default")]
