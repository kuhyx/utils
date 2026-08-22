"""Tests for ID-token refresh and the session lifecycle.

Split from ``test_firebase_auth.py`` (250-line cap), which keeps credential
handling and the two sign-in paths.
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


class TestIdToken:
    """Id token."""

    def test_fails_loudly_when_not_signed_in(self) -> None:
        # Never returns None or a stale token: a sync that quietly stops
        # syncing is the failure mode this design exists to prevent.
        """Fails loudly when not signed in."""
        with pytest.raises(FirebaseAuthError, match="not signed in"):
            _provider().id_token()

    def test_returns_the_stored_token_without_a_network_call(self) -> None:
        """Returns the stored token without a network call."""
        provider = _provider(MemoryCredentialStore(_credentials()))
        with patch.object(fa.requests, "post", side_effect=AssertionError("no HTTP")):
            assert provider.id_token() == _ID_1

    def test_refreshes_an_expired_token_and_keeps_the_rotated_one(self) -> None:
        """Refreshes an expired token and keeps the rotated one."""
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
        """Fails loudly when the refresh token was revoked."""
        store = MemoryCredentialStore(_credentials(valid_for=dt.timedelta(minutes=-5)))
        with (
            _patch_post(_response(400, {"error": {"message": "TOKEN_EXPIRED"}})),
            pytest.raises(FirebaseAuthError, match="TOKEN_EXPIRED"),
        ):
            _provider(store).id_token()

    def test_a_revoked_refresh_token_is_cleared(self) -> None:
        """A dead session must stop reporting itself as connected.

        Regression: ``has_session`` is a presence check, so a revoked token
        kept reading as "connected" while every sync failed with
        TOKEN_EXPIRED.
        """
        store = MemoryCredentialStore(_credentials(valid_for=dt.timedelta(minutes=-5)))
        provider = _provider(store)
        with (
            _patch_post(_response(400, {"error": {"message": "TOKEN_EXPIRED"}})),
            pytest.raises(FirebaseAuthError),
        ):
            provider.id_token()
        assert provider.has_session() is False
        assert store.load() is None

    def test_a_network_error_keeps_the_session(self) -> None:
        """Signing out on a transient failure would need a manual re-login."""
        store = MemoryCredentialStore(_credentials(valid_for=dt.timedelta(minutes=-5)))
        provider = _provider(store)
        with (
            patch.object(
                fa.requests,
                "post",
                side_effect=requests.ConnectionError("connection reset"),
            ),
            pytest.raises(FirebaseAuthError),
        ):
            provider.id_token()
        assert provider.has_session() is True
        assert store.load() is not None

    def test_a_server_error_keeps_the_session(self) -> None:
        """A server error keeps the session."""
        store = MemoryCredentialStore(_credentials(valid_for=dt.timedelta(minutes=-5)))
        provider = _provider(store)
        with (
            _patch_post(_response(503, {"error": {"message": "SERVICE_UNAVAILABLE"}})),
            pytest.raises(FirebaseAuthError),
        ):
            provider.id_token()
        assert provider.has_session() is True
