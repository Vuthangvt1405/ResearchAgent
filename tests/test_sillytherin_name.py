"""The app is SillyTherin everywhere: code, texts, and the names it uses on disk."""

import importlib.util
import subprocess
from pathlib import Path

from sillytherin import config
from sillytherin.__main__ import main
from sillytherin.db import engine as db
from sillytherin.tools import dataset_search
from sillytherin.workspace import store
from sillytherin.workspace.datasets import sources
from sillytherin.workspace.kaggle.callback import CONNECTED_PAGE
from sillytherin.workspace.kernels import PROJECT_LABEL, SCOPE_LABEL

REPO = Path(__file__).resolve().parents[1]
OLD_NAME = "researchchat"
HISTORY_FOLDERS = ("docs/", ".maintenance/")  # plans and reports keep the old name as history
THIS_TEST = "tests/test_sillytherin_name.py"  # it names the old package on purpose

# ---- Renamed to SillyTherin · unit
# Baseline: Given the renamed app and a temporary workspaces folder · When it starts or its files are read


def test_start_command_is_sillytherin():
    # Changed: nothing
    # Then: sillytherin's own module starts the app; researchchat can't be imported
    # Demonstrates: nothing calls across to an old package
    assert main.__module__ == "sillytherin.__main__"
    assert importlib.util.find_spec(OLD_NAME) is None


def test_no_old_name_outside_docs():
    # Changed: nothing
    # Then: no tracked file outside docs/ and .maintenance/ contains researchchat, in any case
    # Demonstrates: the rename is complete
    tracked = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout.split()
    current = [name for name in tracked if not name.startswith(HISTORY_FOLDERS) and name != THIS_TEST and (REPO / name).is_file()]
    mentions = [name for name in current if OLD_NAME in (REPO / name).read_bytes().decode(errors="ignore").lower()]
    assert mentions == []


def test_fresh_start_creates_sillytherin_db(tmp_path):
    # Changed: an empty workspaces folder
    # Then: sillytherin.db appears, with one empty Default project
    # Demonstrates: SillyTherin starts empty under its own name
    root = tmp_path / "workspaces"
    try:
        db.database_for(root)
        project = store.ensure_default_project(root)
        assert (root / "sillytherin.db").is_file()
        assert [p.id for p in store.list_projects(root)] == [project.id] == [store.DEFAULT_PROJECT_ID]
    finally:
        db.close_database(root)


def test_kaggle_token_lives_under_sillytherin():
    # Changed: nothing
    # Then: the sign-in file is <config home>/sillytherin/kaggle-account.json
    # Demonstrates: the old sign-in is not picked up
    assert config.KAGGLE_TOKEN_FILE.parent.name == "sillytherin"
    assert config.KAGGLE_TOKEN_FILE.name == "kaggle-account.json"


def test_kernel_image_and_labels_use_the_new_name():
    # Changed: nothing
    # Then: image sillytherin-kernel:1; container labels sillytherin.*
    # Demonstrates: kernels carry the new name
    assert config.DOCKER_IMAGE == "sillytherin-kernel:1"
    assert (SCOPE_LABEL, PROJECT_LABEL) == ("sillytherin.scope", "sillytherin.project")


def test_texts_say_sillytherin():
    # Changed: nothing
    # Then: system prompt, User-Agent and the Kaggle "connected" page say SillyTherin
    # Demonstrates: what you and other sites read uses the new name
    assert config.SYSTEM_PROMPT.startswith("You are SillyTherin")
    assert sources.USER_AGENT == dataset_search._HEADERS["User-Agent"] == "SillyTherin"
    assert "SillyTherin" in CONNECTED_PAGE


def test_old_database_name_is_not_opened(tmp_path):
    # Changed: a folder holding only researchchat.db
    # Then: the app starts on a new, empty sillytherin.db; the old file is untouched
    # Demonstrates: old data is never read
    root = tmp_path / "workspaces"
    root.mkdir()
    old_database = root / "researchchat.db"
    old_database.write_bytes(b"old rows")
    try:
        db.database_for(root)
        assert store.list_projects(root) == []
        assert (root / "sillytherin.db").is_file() and old_database.read_bytes() == b"old rows"
    finally:
        db.close_database(root)
