"""Tests for the shared Firebase configuration loader.

Every failure mode here is one that would otherwise surface as an
authentication error long after the real mistake (a placeholder left in, a
newline a text editor appended), so each is asserted to name the field at
fault rather than merely to raise.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from crdt_sync import (
    ConfigError,
    FirebaseConfig,
    FirebaseSyncClient,
    credential_store_for,
    mirror_client_for,
)
from crdt_sync._config import _DEFAULT_TIMEOUT_SECONDS, firebase_client_for

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


def test_credential_store_is_per_app() -> None:
    """Two apps must not share one cache file; concurrent writes corrupt it."""
    diet = credential_store_for("diet_guard")
    alarm = credential_store_for("wake_alarm")

    assert diet._path != alarm._path
    assert diet._path.name == "firebase_auth.json"
    assert "diet_guard" in str(diet._path)


def test_client_signs_in_only_without_a_cached_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The common path is a cached refresh token, costing no round trip."""
    config = FirebaseConfig.load(_write(tmp_path / "firebase.json", _VALID))
    sign_ins: list[tuple[str, str]] = []

    class _Auth:
        def __init__(self, api_key: str, _store: object) -> None:
            self.api_key = api_key

        def has_session(self) -> bool:
            """Pretend a cached session exists."""
            return True

        def sign_in(self, email: str, password: str) -> None:
            """Record the sign-in attempt."""
            sign_ins.append((email, password))  # pragma: no cover - must not run

    monkeypatch.setattr("crdt_sync._config.FirebaseTokenProvider", _Auth)
    client = firebase_client_for("diet_guard", config=config)

    assert sign_ins == []
    assert client is not None


def test_client_signs_in_when_there_is_no_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Client signs in when there is no session."""
    config = FirebaseConfig.load(_write(tmp_path / "firebase.json", _VALID))
    password = tmp_path / "password"
    password.write_text("hunter2", encoding="utf-8")
    monkeypatch.setattr("crdt_sync._config.PASSWORD_FILE", password)
    sign_ins: list[tuple[str, str]] = []

    class _Auth:
        def __init__(self, api_key: str, _store: object) -> None:
            self.api_key = api_key

        def has_session(self) -> bool:
            """Pretend no cached session exists."""
            return False

        def sign_in(self, email: str, password_value: str) -> None:
            """Record the credentials the caller signed in with."""
            sign_ins.append((email, password_value))

    monkeypatch.setattr("crdt_sync._config.FirebaseTokenProvider", _Auth)
    firebase_client_for("diet_guard", config=config)

    assert sign_ins == [("sync@example.com", "hunter2")]


def test_mirror_client_makes_firebase_primary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Firebase authoritative, GitHub best-effort -- the cutover shape."""
    config = FirebaseConfig.load(_write(tmp_path / "firebase.json", _VALID))
    github = _StubRemote()

    class _Auth:
        def __init__(self, api_key: str, _store: object) -> None:
            self.api_key = api_key

        def has_session(self) -> bool:
            """Pretend a cached session exists."""
            return True

        def sign_in(self, email: str, password: str) -> None:
            """Record the sign-in attempt."""
            raise AssertionError  # pragma: no cover - must not run

    monkeypatch.setattr("crdt_sync._config.FirebaseTokenProvider", _Auth)
    client = mirror_client_for("diet_guard", github, config=config)

    # Reaching into the wrapper is the point: which backend is authoritative
    # is the one thing a rollback depends on getting right.
    assert client.mirror is github
    assert isinstance(client.primary, FirebaseSyncClient)


def test_client_loads_the_shared_config_when_none_is_given(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default path: apps name themselves and nothing else."""
    monkeypatch.setattr(
        "crdt_sync._config.CONFIG_FILE",
        _write(tmp_path / "firebase.json", _VALID),
    )

    class _Auth:
        def __init__(self, api_key: str, _store: object) -> None:
            self.api_key = api_key

        def has_session(self) -> bool:
            """Pretend a cached session exists."""
            return True

        def sign_in(self, email: str, password: str) -> None:
            """Record the sign-in attempt."""
            raise AssertionError  # pragma: no cover - must not run

    monkeypatch.setattr("crdt_sync._config.FirebaseTokenProvider", _Auth)

    assert firebase_client_for("wake_alarm") is not None


def _client_with_stub_auth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    **kwargs: float,
) -> FirebaseSyncClient:
    """Return a client built with stubbed auth, forwarding ``kwargs``."""
    config = FirebaseConfig.load(_write(tmp_path / "firebase.json", _VALID))

    class _Auth:
        def __init__(self, api_key: str, _store: object) -> None:
            """Record the key; the credential store is irrelevant here."""
            self.api_key = api_key

        def has_session(self) -> bool:
            """Pretend a cached session exists, so no sign-in is attempted."""
            return True

    monkeypatch.setattr("crdt_sync._config.FirebaseTokenProvider", _Auth)
    return firebase_client_for("diet_guard", config=config, **kwargs)


def test_client_uses_the_requested_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A caller's timeout must reach the client, not just the GitHub half."""
    # A keyword with a default adds no branch, so coverage alone cannot tell
    # whether it is actually threaded through to the client.
    client = _client_with_stub_auth(tmp_path, monkeypatch, timeout_seconds=3)

    assert client._timeout_seconds == 3


def test_client_timeout_defaults_to_the_shared_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Omitting the keyword keeps the library-wide default."""
    client = _client_with_stub_auth(tmp_path, monkeypatch)

    assert client._timeout_seconds == _DEFAULT_TIMEOUT_SECONDS
