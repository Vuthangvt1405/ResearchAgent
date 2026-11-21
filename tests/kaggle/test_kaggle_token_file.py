"""The owner-only file that keeps the Kaggle sign-in between restarts."""

import os
import stat

from sillytherin.workspace.kaggle.token_file import SavedSignIn, TokenFile
from tests.kaggle.fakes import CLIENT_ID, REFRESH_TOKEN, USERNAME

SIGN_IN = SavedSignIn(client_id=CLIENT_ID, refresh_token=REFRESH_TOKEN, username=USERNAME, connected_at="2026-11-19T10:00:00Z")


def token_file(tmp_path) -> TokenFile:
    return TokenFile(tmp_path / "config" / "sillytherin" / "kaggle-account.json")


# Baseline: Given a tmp path · When a sign-in is saved and loaded


def test_save_then_load_round_trips(tmp_path) -> None:
    # Changed: — · Then: the same values come back · Demonstrates: the sign-in survives a restart
    file = token_file(tmp_path)
    file.save(SIGN_IN)
    assert TokenFile(file.path).load() == SIGN_IN


def test_file_is_owner_only(tmp_path) -> None:
    # Changed: — · Then: mode 0o600 and the parent folder is created · Demonstrates: only the user can read it
    file = token_file(tmp_path)
    file.save(SIGN_IN)
    assert stat.S_IMODE(file.path.stat().st_mode) == 0o600


def test_save_replaces_atomically(tmp_path) -> None:
    # Changed: saved twice · Then: one file with the second values, no temp file left · Demonstrates: a crash mid-write can't corrupt it
    file = token_file(tmp_path)
    file.save(SIGN_IN)
    second = SavedSignIn(client_id=CLIENT_ID, refresh_token="RT-SECRET-0002", username="bo", connected_at="2026-11-20T10:00:00Z")
    file.save(second)
    assert file.load() == second
    assert sorted(p.name for p in file.path.parent.iterdir()) == ["kaggle-account.json"]


def test_delete_removes_file(tmp_path) -> None:
    # Changed: deleted twice · Then: gone, and the second delete is no error · Demonstrates: disconnect can be repeated
    file = token_file(tmp_path)
    file.save(SIGN_IN)
    file.delete()
    file.delete()
    assert not file.path.exists()


def test_missing_file_is_not_connected(tmp_path) -> None:
    # Changed: no file · Then: None · Demonstrates: first run is not connected
    assert token_file(tmp_path).load() is None


def test_unreadable_json_is_not_connected(tmp_path) -> None:
    # Changed: broken JSON, or no refresh token · Then: None · Demonstrates: a damaged file isn't a crash
    file = token_file(tmp_path)
    file.path.parent.mkdir(parents=True)
    for content in ("{oops", '{"client_id": "x", "username": "ana", "connected_at": "t"}', '["not", "an", "object"]'):
        file.path.write_text(content)
        os.chmod(file.path, 0o600)
        assert file.load() is None


def test_world_readable_file_is_ignored(tmp_path) -> None:
    # Changed: file mode 0644 · Then: None and the file is left as is · Demonstrates: a file others can read isn't used
    file = token_file(tmp_path)
    file.save(SIGN_IN)
    os.chmod(file.path, 0o644)
    assert file.load() is None
    assert file.path.exists()


def test_repr_hides_refresh_token(tmp_path) -> None:
    # Changed: repr of the saved sign-in · Then: the token isn't in the text · Demonstrates: logs and tracebacks stay clean
    assert REFRESH_TOKEN not in repr(SIGN_IN)
    assert USERNAME in repr(SIGN_IN)
