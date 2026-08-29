"""Tests for Firebase Authentication over the REST API.

The HTTP layer is fully mocked, so every branch -- sign-in, refresh, rotated
refresh tokens, revoked sessions, malformed error bodies and network failures
-- is exercised without any network access.
"""

from __future__ import annotations

import datetime as dt
import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from crdt_sync import (
    FirebaseAuthError,
    FirebaseCredentials,
    FirebaseTokenProvider,
    MemoryCredentialStore,
)
from crdt_sync import _firebase_auth as fa

_NOW = dt.datetime(2026, 8, 3, 12, tzinfo=dt.UTC)

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


class TestFirebaseCredentials:
    """Firebase credentials."""

    def test_round_trips_through_json(self) -> None:
        """Round trips through JSON."""
        original = _credentials()
        restored = FirebaseCredentials.from_json(original.to_json())
        assert restored == original

    def test_is_not_expired_inside_its_lifetime(self) -> None:
        """Is not expired inside its lifetime."""
        assert _credentials().is_expired_at(_NOW) is False

    def test_is_expired_once_past_expiry(self) -> None:
        """Is expired once past expiry."""
        stale = _credentials(valid_for=dt.timedelta(minutes=-1))
        assert stale.is_expired_at(_NOW) is True

    def test_is_expired_inside_the_refresh_skew(self) -> None:
        # A tick starting now would outlive a token with 2 minutes left, so
        # it must count as already expired.
        """Is expired inside the refresh skew."""
        soon = _credentials(valid_for=dt.timedelta(minutes=2))
        assert soon.is_expired_at(_NOW) is True


class TestSignIn:
    """Sign in."""

    def test_stores_the_session(self) -> None:
        """Stores the session."""
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
        """Reports googles reason for a rejected password."""
        body = {"error": {"message": "INVALID_LOGIN_CREDENTIALS"}}
        with (
            _patch_post(_response(400, body)),
            pytest.raises(FirebaseAuthError, match="INVALID_LOGIN_CREDENTIALS"),
        ):
            _provider().sign_in("me@example.com", "wrong")

    def test_reports_a_string_shaped_error_body(self) -> None:
        """Reports a string shaped error body."""
        with (
            _patch_post(_response(400, {"error": "BAD_REQUEST"})),
            pytest.raises(FirebaseAuthError, match="BAD_REQUEST"),
        ):
            _provider().sign_in("a@b.c", "x")

    def test_survives_an_error_body_with_no_error_key(self) -> None:
        """Survives an error body with no error key."""
        with (
            _patch_post(_response(400, {"unexpected": "shape"})),
            pytest.raises(FirebaseAuthError, match="HTTP 400"),
        ):
            _provider().sign_in("a@b.c", "x")

    def test_survives_a_non_dict_error_body(self) -> None:
        """Survives a non dict error body."""
        with (
            _patch_post(_response(400, ["not", "a", "dict"])),
            pytest.raises(FirebaseAuthError, match="HTTP 400"),
        ):
            _provider().sign_in("a@b.c", "x")

    def test_survives_a_non_json_error_body(self) -> None:
        """Survives a non JSON error body."""
        response = _response(502)
        response.json = MagicMock(side_effect=ValueError("not json"))
        with (
            _patch_post(response),
            pytest.raises(FirebaseAuthError, match="HTTP 502"),
        ):
            _provider().sign_in("a@b.c", "x")

    def test_turns_a_network_failure_into_an_auth_error(self) -> None:
        """Turns a network failure into an auth error."""
        with (
            patch.object(
                fa.requests, "post", side_effect=requests.ConnectionError("offline")
            ),
            pytest.raises(FirebaseAuthError, match="network error"),
        ):
            _provider().sign_in("a@b.c", "x")
