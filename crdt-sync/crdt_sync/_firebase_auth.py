"""Firebase Authentication over its REST API, with no SDK dependency.

The Firebase Admin SDK authenticates with a service-account key, which
bypasses security rules entirely and would have to be distributed to every
device. These are single-user personal apps, so devices instead sign in as
one ordinary user and hold a refresh token -- the same path the Flutter side
takes, so both platforms behave identically.

Mirrors ``crdt_sync_dart``'s ``lib/src/firebase_auth_rest.dart``; keep the
two in step.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import json
from typing import TYPE_CHECKING, Protocol

import requests as _requests

from crdt_sync._autherrors import FirebaseAuthError, _is_revoked, _reason
from crdt_sync._credentials import (
    CredentialStore,
    FileCredentialStore,
    FirebaseCredentials,
    MemoryCredentialStore,
    _utcnow,
)
from crdt_sync._http import new_session

# Bound to the name ``requests`` so the call sites below -- and the tests
# that patch ``<module>.requests.<verb>`` -- are unchanged by pooling.
requests = new_session()


if TYPE_CHECKING:
    from pathlib import Path

_SIGN_IN_BASE = "https://identitytoolkit.googleapis.com/v1"
_REFRESH_BASE = "https://securetoken.googleapis.com/v1"
_DEFAULT_TIMEOUT_SECONDS = 15



class FirebaseTokenProvider:
    """Signs in and keeps a valid ID token available, refreshing as needed.

    ``api_key`` is the project's public Web API key -- not a secret, and safe
    to ship inside an APK. The actual credential is the refresh token held by
    the store.
    """

    def __init__(
        self,
        api_key: str,
        store: CredentialStore,
        *,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        clock: object = None,
    ) -> None:
        """Create a provider for ``api_key`` persisting through ``store``.

        Args:
            api_key: The project's public Web API key.
            store: Where the refresh token lives between runs.
            timeout_seconds: Per-request network timeout.
            clock: A zero-arg callable returning "now" (tests inject one).
        """
        self._api_key = api_key
        self._store = store
        self._timeout_seconds = timeout_seconds
        self._clock = clock if callable(clock) else _utcnow
        self._cached: FirebaseCredentials | None = None

    def sign_in(self, email: str, password: str) -> None:
        """Exchange an email/password for a session and persist it.

        Called once per device from a setup command; every later run reuses
        the stored refresh token.

        Raises:
            FirebaseAuthError: If the credentials are rejected.
        """
        body = self._post(
            f"{_SIGN_IN_BASE}/accounts:signInWithPassword?key={self._api_key}",
            {"email": email, "password": password, "returnSecureToken": True},
            "sign in",
        )
        self._adopt(
            id_token=body["idToken"],
            refresh_token=body["refreshToken"],
            expires_in_seconds=body["expiresIn"],
        )

    def sign_in_with_google(self, id_token: str, expected_uid: str = "") -> str:
        """Exchange a Google ID token for a session and persist it.

        Mirrors ``crdt_sync_dart``'s ``signInWithGoogle``. Used to reseed a
        machine's session after the sync account moved to Google-only sign-in:
        the refresh token this stores is what keeps a headless job working
        between runs, so the browser flow is needed once per machine, not once
        per tick.

        Deliberately *not* a service-account key. That would authenticate as
        an admin and bypass the security rules entirely, so the pinned-uid
        rule that protects this data would stop applying to every PC write.

        Args:
            id_token: A Google ID token whose audience is this project.
            expected_uid: When given, asserted against the uid Firebase
                returns. A mismatch raises without storing anything -- an
                unlinked Google identity is *signed up* rather than refused,
                and that session would then be denied every read and write.

        Returns:
            The email Firebase reports for the account.

        Raises:
            FirebaseAuthError: If the token is rejected, or resolves to a uid
                other than ``expected_uid``.
        """
        body = self._post(
            f"{_SIGN_IN_BASE}/accounts:signInWithIdp?key={self._api_key}",
            {
                # The IdP credential travels form-encoded, not as JSON -- an
                # identitytoolkit quirk. Sending it as a field returns
                # INVALID_IDP_RESPONSE, which reads like a bad token.
                "postBody": f"id_token={id_token}&providerId=google.com",
                "requestUri": "http://localhost",
                "returnSecureToken": True,
            },
            "sign in with Google",
        )
        uid = body.get("localId", "")
        if expected_uid and uid != expected_uid:
            msg = (
                f"signed in as the wrong account: Google resolved to uid "
                f"{uid!r}, but this data belongs to {expected_uid!r}"
            )
            raise FirebaseAuthError(msg)
        self._adopt(
            id_token=body["idToken"],
            refresh_token=body["refreshToken"],
            expires_in_seconds=body["expiresIn"],
        )
        return str(body.get("email", ""))

    def id_token(self) -> str:
        """Return a currently-valid ID token, refreshing if needed.

        Never returns a stale token and never silently no-ops: a sync that
        quietly stops syncing is the failure mode this design exists to
        prevent.

        Raises:
            FirebaseAuthError: If no session is stored, or the refresh token
                has been revoked.
        """
        credentials = self._load()
        if credentials is None:
            msg = "not signed in: no stored refresh token for this device"
            raise FirebaseAuthError(msg)
        if not credentials.is_expired_at(self._clock()):
            return credentials.id_token
        return self._refresh(credentials.refresh_token)

    def has_session(self) -> bool:
        """Return whether this device has a stored session at all.

        Distinguishes "sync is not configured" -- a normal state for
        ``screen-locker`` -- from "sync is configured and broken", an error.
        """
        return self._load() is not None

    def sign_out(self) -> None:
        """Forget the stored session, so the next token request fails."""
        self._cached = None
        self._store.clear()

    def _load(self) -> FirebaseCredentials | None:
        if self._cached is None:
            self._cached = self._store.load()
        return self._cached

    def _refresh(self, refresh_token: str) -> str:
        try:
            body = self._post(
                f"{_REFRESH_BASE}/token?key={self._api_key}",
                {"grant_type": "refresh_token", "refresh_token": refresh_token},
                "refresh the session",
            )
        except FirebaseAuthError as error:
            # A revoked refresh token never becomes valid again, so keeping it
            # is what let a dead device report "connected" and then fail every
            # sync with TOKEN_EXPIRED. Drop it so has_session() is honest.
            if _is_revoked(error):
                self.sign_out()
            raise
        return self._adopt(
            id_token=body["id_token"],
            # A refresh may hand back a rotated token; keep the new one.
            refresh_token=body["refresh_token"],
            expires_in_seconds=body["expires_in"],
        )

    def _adopt(
        self,
        *,
        id_token: str,
        refresh_token: str,
        expires_in_seconds: str,
    ) -> str:
        credentials = FirebaseCredentials(
            id_token=id_token,
            refresh_token=refresh_token,
            expires_at=self._clock() + dt.timedelta(seconds=int(expires_in_seconds)),
        )
        self._cached = credentials
        self._store.save(credentials)
        return id_token

    def _post(
        self,
        url: str,
        payload: dict[str, object],
        what: str,
    ) -> dict[str, str]:
        try:
            response = requests.post(
                url,
                json=payload,
                timeout=self._timeout_seconds,
            )
        except _requests.RequestException as exc:
            msg = f"network error trying to {what}"
            raise FirebaseAuthError(msg) from exc
        if not response.ok:
            reason = _reason(response)
            msg = f"failed to {what}: HTTP {response.status_code}{reason}"
            raise FirebaseAuthError(msg)
        return response.json()
