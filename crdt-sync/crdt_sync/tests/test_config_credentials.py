"""Tests for reading the sync password and building a client from config.

Split from ``test_config.py`` (250-line cap), which keeps loading and
validating the config document itself.
"""

# These tests assert on private attributes on purpose: `_timeout_seconds`
# and `_path` are exactly what the fixes under test set, and there is no
# public accessor for either.
# pylint: disable=protected-access

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from crdt_sync import (
    ConfigError,
    FirebaseConfig,
)

if TYPE_CHECKING:
    from pathlib import Path

_VALID = {
    "apiKey": "AIzaSyExample",
    "databaseUrl": "https://kuhy-syncs-default-rtdb.europe-west1.firebasedatabase.app",
    "projectId": "kuhy-syncs",
    "uid": "OvA2REQyLIhAHOEjzwS1o877rgG3",
    "email": "sync@example.com",
}


class _StubRemote:
    """A do-nothing :class:`~crdt_sync.RemoteStore`, standing in for GitHub.

    A real implementation rather than a bare ``object()`` so the type checker
    accepts it without a suppression.
    """

    def list_directory(self, _path: str) -> list[str]:
        """Report an empty remote directory."""
        return []

    def get_file_text(self, _path: str) -> str | None:
        """Report the file as absent."""
        return None

    def put_file_text(self, path: str, text: str, *, message: str) -> None:
        """Accept and discard a write."""

    def delete_file(self, path: str, *, message: str = "") -> None:
        """Accept and discard a delete."""

    def can_access_remote(self) -> bool:
        """Report the remote as reachable."""
        return True


def _write(path: Path, data: object) -> Path:
    """Write ``data`` as JSON to ``path`` and return it."""
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_reads_a_password(tmp_path: Path) -> None:
    """Reads a password."""
    config = FirebaseConfig.load(_write(tmp_path / "firebase.json", _VALID))
    password = tmp_path / "password"
    password.write_text("hunter2", encoding="utf-8")

    assert config.read_password(password) == "hunter2"


def test_strips_a_trailing_newline_from_the_password(tmp_path: Path) -> None:
    """The likeliest hand-editing mistake, and otherwise invisible."""
    config = FirebaseConfig.load(_write(tmp_path / "firebase.json", _VALID))
    password = tmp_path / "password"
    password.write_text("hunter2\n", encoding="utf-8")

    assert config.read_password(password) == "hunter2"


def test_rejects_an_empty_password(tmp_path: Path) -> None:
    """Rejects an empty password."""
    config = FirebaseConfig.load(_write(tmp_path / "firebase.json", _VALID))
    password = tmp_path / "password"
    password.write_text("   ", encoding="utf-8")

    with pytest.raises(ConfigError, match="empty or still holds"):
        config.read_password(password)


def test_rejects_a_placeholder_password(tmp_path: Path) -> None:
    """Rejects a placeholder password."""
    config = FirebaseConfig.load(_write(tmp_path / "firebase.json", _VALID))
    password = tmp_path / "password"
    password.write_text("PASTE_SYNC_ACCOUNT_PASSWORD_HERE", encoding="utf-8")

    with pytest.raises(ConfigError, match="placeholder"):
        config.read_password(password)


def test_reports_an_unreadable_password(tmp_path: Path) -> None:
    """Reports an unreadable password."""
    config = FirebaseConfig.load(_write(tmp_path / "firebase.json", _VALID))
    (tmp_path / "password").mkdir()

    with pytest.raises(ConfigError, match="could not be read"):
        config.read_password(tmp_path / "password")
