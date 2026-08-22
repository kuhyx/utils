"""Tests for the shared Firebase configuration loader.

Every failure mode here is one that would otherwise surface as an
authentication error long after the real mistake (a placeholder left in, a
newline a text editor appended), so each is asserted to name the field at
fault rather than merely to raise.
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


def test_loads_a_valid_config(tmp_path: Path) -> None:
    """Loads a valid config."""
    config = FirebaseConfig.load(_write(tmp_path / "firebase.json", _VALID))

    assert config.api_key == "AIzaSyExample"
    assert config.project_id == "kuhy-syncs"
    assert config.uid == "OvA2REQyLIhAHOEjzwS1o877rgG3"
    assert config.email == "sync@example.com"
    assert config.database_url.endswith("europe-west1.firebasedatabase.app")


def test_ignores_the_scaffold_comment_keys(tmp_path: Path) -> None:
    """The shipped scaffold explains each field inline; that is not config."""
    annotated = {**_VALID, "_comment_apiKey": "where to find it", "_comment": "x"}

    config = FirebaseConfig.load(_write(tmp_path / "firebase.json", annotated))

    assert config.api_key == "AIzaSyExample"


def test_reports_a_missing_file(tmp_path: Path) -> None:
    """Reports a missing file."""
    with pytest.raises(ConfigError, match="does not exist"):
        FirebaseConfig.load(tmp_path / "absent.json")


def test_reports_unreadable_json(tmp_path: Path) -> None:
    """Reports unreadable JSON."""
    path = tmp_path / "firebase.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ConfigError, match="not valid JSON"):
        FirebaseConfig.load(path)


def test_reports_a_non_object_document(tmp_path: Path) -> None:
    """Reports a non object document."""
    with pytest.raises(ConfigError, match="must contain a JSON object"):
        FirebaseConfig.load(_write(tmp_path / "firebase.json", ["a list"]))


def test_reports_an_unreadable_path(tmp_path: Path) -> None:
    """A directory where a file belongs is an OSError, not a missing file."""
    (tmp_path / "firebase.json").mkdir()

    with pytest.raises(ConfigError, match="could not be read"):
        FirebaseConfig.load(tmp_path / "firebase.json")


@pytest.mark.parametrize("field", sorted(_VALID))
def test_names_a_missing_field(tmp_path: Path, field: str) -> None:
    """Names a missing field."""
    incomplete = {k: v for k, v in _VALID.items() if k != field}

    with pytest.raises(ConfigError, match=field):
        FirebaseConfig.load(_write(tmp_path / "firebase.json", incomplete))


def test_names_an_empty_field(tmp_path: Path) -> None:
    """Names an empty field."""
    with pytest.raises(ConfigError, match="uid"):
        FirebaseConfig.load(_write(tmp_path / "firebase.json", {**_VALID, "uid": "  "}))


def test_names_an_unfilled_placeholder(tmp_path: Path) -> None:
    """The exact state the scaffold ships in must not load silently."""
    unfilled = {**_VALID, "apiKey": "PASTE_WEB_API_KEY_HERE"}

    with pytest.raises(ConfigError, match=r"placeholder for: apiKey"):
        FirebaseConfig.load(_write(tmp_path / "firebase.json", unfilled))
