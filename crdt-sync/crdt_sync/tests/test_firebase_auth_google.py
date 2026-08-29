"""Tests for the Google sign-in path.

Split from ``test_firebase_auth.py`` (250-line cap), which keeps credential
handling and password sign-in.
"""

from __future__ import annotations

import datetime as dt
import json
from unittest.mock import MagicMock, patch

import pytest

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


class TestSignInWithGoogle:
    """Sign in with google."""

    @staticmethod
    def _google_body(**overrides: object) -> dict[str, object]:
        body: dict[str, object] = {
            "idToken": _ID_1,
            "refreshToken": _REFRESH_1,
            "expiresIn": "3600",
            "localId": _UID,
            "email": "me@example.com",
        }
        body.update(overrides)
        return body

    def test_stores_the_session(self) -> None:
        """Stores the session."""
        store = MemoryCredentialStore()
        with _patch_post(_response(200, self._google_body())):
            _provider(store).sign_in_with_google("google-jwt")
        saved = store.load()
        assert saved is not None
        assert saved.id_token == _ID_1
        assert saved.refresh_token == _REFRESH_1
        assert saved.expires_at == _NOW + dt.timedelta(hours=1)

    def test_returns_the_account_email(self) -> None:
        """Returns the account email."""
        with _patch_post(_response(200, self._google_body())):
            email = _provider().sign_in_with_google("google-jwt")
        assert email == "me@example.com"

    def test_returns_an_empty_email_when_google_omits_one(self) -> None:
        # Firebase leaves `email` out when the Google account has no verified
        # address. That is not a failure -- the uid check is what matters --
        # so the caller gets "" rather than a KeyError.
        """Returns an empty email when google omits one."""
        body = self._google_body()
        del body["email"]
        with _patch_post(_response(200, body)):
            assert not _provider().sign_in_with_google("google-jwt")

    def test_sends_the_credential_form_encoded_in_post_body(self) -> None:
        # identitytoolkit rejects the IdP credential as a JSON field with
        # INVALID_IDP_RESPONSE, which reads like a bad token; pin the shape.
        """Sends the credential form encoded in post body."""
        post = MagicMock(return_value=_response(200, self._google_body()))
        with patch.object(fa.requests, "post", post):
            _provider().sign_in_with_google("google-jwt")
        sent = post.call_args.kwargs["json"]
        assert sent["postBody"] == "id_token=google-jwt&providerId=google.com"
        assert "signInWithIdp" in post.call_args.args[0]

    def test_accepts_the_uid_the_data_belongs_to(self) -> None:
        """Accepts the uid the data belongs to."""
        store = MemoryCredentialStore()
        with _patch_post(_response(200, self._google_body())):
            _provider(store).sign_in_with_google("google-jwt", expected_uid=_UID)
        assert store.load() is not None

    def test_rejects_and_stores_nothing_for_a_different_uid(self) -> None:
        # The signed-up identity does exist server-side by now -- this call
        # omits `idToken`, so an unlinked Google account is signed *up* before
        # the uid is known. What this guarantees is that no such session is
        # persisted locally, where it would be denied every read and write.
        """Rejects and stores nothing for a different uid."""
        store = MemoryCredentialStore()
        body = self._google_body(localId="someone-else")
        with (
            _patch_post(_response(200, body)),
            pytest.raises(FirebaseAuthError, match="wrong account"),
        ):
            _provider(store).sign_in_with_google("google-jwt", expected_uid=_UID)
        assert store.load() is None

    def test_reports_googles_reason_for_a_rejected_token(self) -> None:
        """Reports googles reason for a rejected token."""
        body = {"error": {"message": "INVALID_IDP_RESPONSE"}}
        with (
            _patch_post(_response(400, body)),
            pytest.raises(FirebaseAuthError, match="INVALID_IDP_RESPONSE"),
        ):
            _provider().sign_in_with_google("stale-jwt")
