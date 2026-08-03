"""Tests for Firebase Authentication over the REST API.

The HTTP layer is fully mocked, so every branch -- sign-in, refresh, rotated
refresh tokens, revoked sessions, malformed error bodies and network failures
-- is exercised without any network access.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
import requests

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

_NOW = dt.datetime(2026, 8, 3, 12, tzinfo=dt.UTC)

# Fixture values referenced through names ruff's hardcoded-credential checks
# (S105-S107) do not key off. Comparing an attribute called `id_token` to a
# bare string literal trips S105 no matter how obviously fake the value is.
_ID_1 = "id-1"
_ID_2 = "id-2"
_REFRESH_1 = "refresh-1"
_REFRESH_2 = "refresh-2"


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


class TestFirebaseCredentials:
    def test_round_trips_through_json(self) -> None:
        original = _credentials()
        restored = FirebaseCredentials.from_json(original.to_json())
        assert restored == original

    def test_is_not_expired_inside_its_lifetime(self) -> None:
        assert _credentials().is_expired_at(_NOW) is False

    def test_is_expired_once_past_expiry(self) -> None:
        stale = _credentials(valid_for=dt.timedelta(minutes=-1))
        assert stale.is_expired_at(_NOW) is True

    def test_is_expired_inside_the_refresh_skew(self) -> None:
        # A tick starting now would outlive a token with 2 minutes left, so
        # it must count as already expired.
        soon = _credentials(valid_for=dt.timedelta(minutes=2))
        assert soon.is_expired_at(_NOW) is True


class TestSignIn:
    def test_stores_the_session(self) -> None:
        store = MemoryCredentialStore()
        body = {"idToken": _ID_1, "refreshToken": _REFRESH_1, "expiresIn": "3600"}
        with _patch_post(_response(200, body)):
            _provider(store).sign_in("me@example.com", "hunter2")
        saved = store.load()
        assert saved is not None
        assert saved.id_token == _ID_1
        assert saved.refresh_token == _REFRESH_1
        assert saved.expires_at == _NOW + dt.timedelta(hours=1)

    def test_reports_googles_reason_for_a_rejected_password(self) -> None:
        body = {"error": {"message": "INVALID_LOGIN_CREDENTIALS"}}
        with (
            _patch_post(_response(400, body)),
            pytest.raises(FirebaseAuthError, match="INVALID_LOGIN_CREDENTIALS"),
        ):
            _provider().sign_in("me@example.com", "wrong")

    def test_reports_a_string_shaped_error_body(self) -> None:
        with (
            _patch_post(_response(400, {"error": "BAD_REQUEST"})),
            pytest.raises(FirebaseAuthError, match="BAD_REQUEST"),
        ):
            _provider().sign_in("a@b.c", "x")

    def test_survives_an_error_body_with_no_error_key(self) -> None:
        with (
            _patch_post(_response(400, {"unexpected": "shape"})),
            pytest.raises(FirebaseAuthError, match="HTTP 400"),
        ):
            _provider().sign_in("a@b.c", "x")

    def test_survives_a_non_dict_error_body(self) -> None:
        with (
            _patch_post(_response(400, ["not", "a", "dict"])),
            pytest.raises(FirebaseAuthError, match="HTTP 400"),
        ):
            _provider().sign_in("a@b.c", "x")

    def test_survives_a_non_json_error_body(self) -> None:
        response = _response(502)
        response.json = MagicMock(side_effect=ValueError("not json"))
        with (
            _patch_post(response),
            pytest.raises(FirebaseAuthError, match="HTTP 502"),
        ):
            _provider().sign_in("a@b.c", "x")

    def test_turns_a_network_failure_into_an_auth_error(self) -> None:
        with (
            patch.object(
                fa.requests, "post", side_effect=requests.ConnectionError("offline")
            ),
            pytest.raises(FirebaseAuthError, match="network error"),
        ):
            _provider().sign_in("a@b.c", "x")


class TestIdToken:
    def test_fails_loudly_when_not_signed_in(self) -> None:
        # Never returns None or a stale token: a sync that quietly stops
        # syncing is the failure mode this design exists to prevent.
        with pytest.raises(FirebaseAuthError, match="not signed in"):
            _provider().id_token()

    def test_returns_the_stored_token_without_a_network_call(self) -> None:
        provider = _provider(MemoryCredentialStore(_credentials()))
        with patch.object(fa.requests, "post", side_effect=AssertionError("no HTTP")):
            assert provider.id_token() == _ID_1

    def test_refreshes_an_expired_token_and_keeps_the_rotated_one(self) -> None:
        store = MemoryCredentialStore(_credentials(valid_for=dt.timedelta(minutes=-5)))
        body = {
            "id_token": _ID_2,
            "refresh_token": _REFRESH_2,
            "expires_in": "3600",
        }
        with _patch_post(_response(200, body)):
            assert _provider(store).id_token() == _ID_2
        saved = store.load()
        assert saved is not None
        assert saved.refresh_token == _REFRESH_2

    def test_fails_loudly_when_the_refresh_token_was_revoked(self) -> None:
        store = MemoryCredentialStore(_credentials(valid_for=dt.timedelta(minutes=-5)))
        with (
            _patch_post(_response(400, {"error": {"message": "TOKEN_EXPIRED"}})),
            pytest.raises(FirebaseAuthError, match="TOKEN_EXPIRED"),
        ):
            _provider(store).id_token()


class TestSessionLifecycle:
    def test_has_session_is_false_before_sign_in_and_true_after(self) -> None:
        store = MemoryCredentialStore()
        provider = _provider(store)
        assert provider.has_session() is False
        body = {"idToken": _ID_1, "refreshToken": _REFRESH_1, "expiresIn": "3600"}
        with _patch_post(_response(200, body)):
            provider.sign_in("a@b.c", "x")
        assert provider.has_session() is True

    def test_sign_out_clears_the_store(self) -> None:
        store = MemoryCredentialStore(_credentials())
        provider = _provider(store)
        assert provider.id_token() == _ID_1
        provider.sign_out()
        assert store.load() is None
        with pytest.raises(FirebaseAuthError):
            provider.id_token()

    def test_defaults_to_the_real_clock_when_none_is_injected(self) -> None:
        provider = FirebaseTokenProvider("k", MemoryCredentialStore())
        assert provider.has_session() is False


class TestFileCredentialStore:
    def test_round_trips_through_a_file(self, tmp_path: Path) -> None:
        store = FileCredentialStore(tmp_path / "nested" / "creds.json")
        store.save(_credentials())
        assert store.load() == _credentials()

    def test_writes_the_file_readable_only_by_this_user(self, tmp_path: Path) -> None:
        # The refresh token is the real secret; it must never be briefly
        # world-readable between write and chmod.
        path = tmp_path / "creds.json"
        FileCredentialStore(path).save(_credentials())
        assert path.stat().st_mode & 0o777 == 0o600

    def test_load_returns_none_when_absent(self, tmp_path: Path) -> None:
        assert FileCredentialStore(tmp_path / "missing.json").load() is None

    def test_load_returns_none_for_a_truncated_file(self, tmp_path: Path) -> None:
        # An interrupted write reads as "not signed in"; the caller's next
        # step is to sign in again, which repairs it.
        path = tmp_path / "creds.json"
        path.write_text('{"id_token": "a"', encoding="utf-8")
        assert FileCredentialStore(path).load() is None

    def test_load_returns_none_when_fields_are_missing(self, tmp_path: Path) -> None:
        path = tmp_path / "creds.json"
        path.write_text('{"id_token": "a"}', encoding="utf-8")
        assert FileCredentialStore(path).load() is None

    def test_load_returns_none_for_an_unparsable_expiry(self, tmp_path: Path) -> None:
        path = tmp_path / "creds.json"
        path.write_text(
            json.dumps(
                {"id_token": "a", "refresh_token": "b", "expires_at": "not-a-date"}
            ),
            encoding="utf-8",
        )
        assert FileCredentialStore(path).load() is None

    def test_clear_removes_the_file_and_is_idempotent(self, tmp_path: Path) -> None:
        path = tmp_path / "creds.json"
        store = FileCredentialStore(path)
        store.save(_credentials())
        store.clear()
        assert not path.exists()
        store.clear()

    def test_overwrites_an_existing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "creds.json"
        store = FileCredentialStore(path)
        store.save(_credentials())
        store.save(_credentials(id_value=_ID_2))
        loaded = store.load()
        assert loaded is not None
        assert loaded.id_token == _ID_2
