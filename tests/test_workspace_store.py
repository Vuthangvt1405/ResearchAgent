"""Projects and notebook files on disk.

Plan: docs/plans/done/notebook-workspace-plan.md section 7.
"""

import json

import nbformat
import pytest

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


def test_new_project_has_empty_notebook_and_files_dir(root):
    # G1✅1 (baseline) · Demonstrates: a project is a self-contained workspace
    project = store.create_project("Tokyo housing", root)
    folder = root / project.id
    assert project.id == "tokyo-housing"
    assert json.loads((folder / "project.json").read_text("utf-8"))["name"] == "Tokyo housing"
    assert (folder / "files").is_dir()
    nb = store.load_notebook(project.id, root)
    assert nb.cells == []
    assert store.get_version(nb) == 0


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
