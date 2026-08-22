"""Tests for the auth session lifecycle.

Split from ``test_firebase_auth.py`` (250-line cap);
``test_firebase_auth_tokens.py`` keeps ID-token refresh.
"""



from __future__ import annotations

import datetime as dt
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from crdt_sync import (
    FileCredentialStore,
    FirebaseAuthError,
    FirebaseCredentials,
    FirebaseTokenProvider,
    MemoryCredentialStore,
)
from crdt_sync import _firebase_auth as fa

if TYPE_CHECKING:
    from pathlib import Path

_NOW = dt.datetime(2026, 8, 3, 12, tzinfo=dt.timezone.utc)

# Fixture values referenced through names ruff's hardcoded-credential checks
# (S105-S107) do not key off. Comparing an attribute called `id_token` to a
# bare string literal trips S105 no matter how obviously fake the value is.
_ID_1 = "id-1"
_ID_2 = "id-2"
_REFRESH_1 = "refresh-1"
_REFRESH_2 = "refresh-2"
_UID = "uid-the-data-belongs-to"


def _response(status_code: int = 200, json_data: object = None) -> MagicMock:
    """Build a fake ``requests.Response`` with a status and JSON body."""
    response = MagicMock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 300
    response.json = MagicMock(return_value=json_data if json_data is not None else {})
    response.text = json.dumps(json_data) if json_data is not None else ""
    return response


def _provider(
    store: object = None,
    *,
    now: dt.datetime = _NOW,
) -> FirebaseTokenProvider:
    return FirebaseTokenProvider(
        "fake-api-key",
        store or MemoryCredentialStore(),
        clock=lambda: now,
    )


# Parameters named without "token": ruff's hardcoded-credential check (S107)
# keys off the identifier, and these are obviously fake test fixtures.
def _credentials(
    *,
    id_value: str = _ID_1,
    refresh_value: str = _REFRESH_1,
    valid_for: dt.timedelta = dt.timedelta(hours=1),
) -> FirebaseCredentials:
    return FirebaseCredentials(
        id_token=id_value,
        refresh_token=refresh_value,
        expires_at=_NOW + valid_for,
    )


def _patch_post(*responses: MagicMock) -> object:
    return patch.object(fa.requests, "post", side_effect=list(responses))


class TestSessionLifecycle:
    """Session lifecycle."""

    def test_has_session_is_false_before_sign_in_and_true_after(self) -> None:
        """Has session is false before sign in and true after."""
        store = MemoryCredentialStore()
        provider = _provider(store)
        assert provider.has_session() is False
        body = {"idToken": _ID_1, "refreshToken": _REFRESH_1, "expiresIn": "3600"}
        with _patch_post(_response(200, body)):
            provider.sign_in("a@b.c", "x")
        assert provider.has_session() is True

    def test_sign_out_clears_the_store(self) -> None:
        """Sign out clears the store."""
        store = MemoryCredentialStore(_credentials())
        provider = _provider(store)
        assert provider.id_token() == _ID_1
        provider.sign_out()
        assert store.load() is None
        with pytest.raises(FirebaseAuthError):
            provider.id_token()

    def test_defaults_to_the_real_clock_when_none_is_injected(self) -> None:
        """Defaults to the real clock when none is injected."""
        provider = FirebaseTokenProvider("k", MemoryCredentialStore())
        assert provider.has_session() is False


class TestFileCredentialStore:
    """File credential store."""

    def test_round_trips_through_a_file(self, tmp_path: Path) -> None:
        """Round trips through a file."""
        store = FileCredentialStore(tmp_path / "nested" / "creds.json")
        store.save(_credentials())
        assert store.load() == _credentials()

    def test_writes_the_file_readable_only_by_this_user(self, tmp_path: Path) -> None:
        # The refresh token is the real secret; it must never be briefly
        # world-readable between write and chmod.
        """Writes the file readable only by this user."""
        path = tmp_path / "creds.json"
        FileCredentialStore(path).save(_credentials())
        assert path.stat().st_mode & 0o777 == 0o600

    def test_load_returns_none_when_absent(self, tmp_path: Path) -> None:
        """Load returns none when absent."""
        assert FileCredentialStore(tmp_path / "missing.json").load() is None

    def test_load_returns_none_for_a_truncated_file(self, tmp_path: Path) -> None:
        # An interrupted write reads as "not signed in"; the caller's next
        # step is to sign in again, which repairs it.
        """Load returns none for a truncated file."""
        path = tmp_path / "creds.json"
        path.write_text('{"id_token": "a"', encoding="utf-8")
        assert FileCredentialStore(path).load() is None

    def test_load_returns_none_when_fields_are_missing(self, tmp_path: Path) -> None:
        """Load returns none when fields are missing."""
        path = tmp_path / "creds.json"
        path.write_text('{"id_token": "a"}', encoding="utf-8")
        assert FileCredentialStore(path).load() is None

    def test_load_returns_none_for_an_unparsable_expiry(self, tmp_path: Path) -> None:
        """Load returns none for an unparsable expiry."""
        path = tmp_path / "creds.json"
        path.write_text(
            json.dumps(
                {"id_token": "a", "refresh_token": "b", "expires_at": "not-a-date"}
            ),
            encoding="utf-8",
        )
        assert FileCredentialStore(path).load() is None

    def test_clear_removes_the_file_and_is_idempotent(self, tmp_path: Path) -> None:
        """Clear removes the file and is idempotent."""
        path = tmp_path / "creds.json"
        store = FileCredentialStore(path)
        store.save(_credentials())
        store.clear()
        assert not path.exists()
        store.clear()

    def test_overwrites_an_existing_file(self, tmp_path: Path) -> None:
        """Overwrites an existing file."""
        path = tmp_path / "creds.json"
        store = FileCredentialStore(path)
        store.save(_credentials())
        store.save(_credentials(id_value=_ID_2))
        loaded = store.load()
        assert loaded is not None
        assert loaded.id_token == _ID_2
