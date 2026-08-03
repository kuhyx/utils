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

import requests

from crdt_sync._remote import RemoteSyncError

if TYPE_CHECKING:
    from pathlib import Path

_SIGN_IN_BASE = "https://identitytoolkit.googleapis.com/v1"
_REFRESH_BASE = "https://securetoken.googleapis.com/v1"
_DEFAULT_TIMEOUT_SECONDS = 15

# Refresh this long before the token actually expires. An ID token lives ~1h;
# refreshing early means a tick that starts just under the wire still finishes
# with a valid token rather than 401ing halfway through a multi-file push.
_REFRESH_SKEW = dt.timedelta(minutes=5)


class FirebaseAuthError(RemoteSyncError):
    """Raised for an authentication failure the caller must not ignore.

    A :class:`crdt_sync.RemoteSyncError` so callers that only care about
    "sync is broken" can catch one type, while a settings screen can single
    this out to say "your password is wrong" rather than "the network is
    down".
    """


@dataclass(frozen=True)
class FirebaseCredentials:
    """One device's session: a short-lived ID token plus its refresh token.

    Attributes:
    ----------
    id_token:
        The bearer credential for Realtime Database requests. Expires fast.
    refresh_token:
        The long-lived credential. **This is the secret worth protecting.**
    expires_at:
        When ``id_token`` stops being accepted, in UTC.
    """

    id_token: str
    refresh_token: str
    expires_at: dt.datetime

    def is_expired_at(self, now: dt.datetime) -> bool:
        """Return whether the token is expired, or close enough to it."""
        return now + _REFRESH_SKEW >= self.expires_at

    def to_json(self) -> dict[str, str]:
        """Return a JSON-serializable form."""
        return {
            "id_token": self.id_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at.isoformat(),
        }

    @classmethod
    def from_json(cls, data: dict[str, str]) -> FirebaseCredentials:
        """Rebuild credentials from :meth:`to_json` output."""
        return cls(
            id_token=data["id_token"],
            refresh_token=data["refresh_token"],
            expires_at=dt.datetime.fromisoformat(data["expires_at"]),
        )


class CredentialStore(Protocol):
    """Where a device keeps its credentials between runs."""

    def load(self) -> FirebaseCredentials | None:
        """Return the stored credentials, or ``None`` if not signed in."""

    def save(self, credentials: FirebaseCredentials) -> None:
        """Persist ``credentials``."""

    def clear(self) -> None:
        """Forget any stored credentials."""


class MemoryCredentialStore:
    """A :class:`CredentialStore` for tests and one-shot scripts."""

    def __init__(self, credentials: FirebaseCredentials | None = None) -> None:
        """Start holding ``credentials`` (or nothing)."""
        self._credentials = credentials

    def load(self) -> FirebaseCredentials | None:
        """Return the held credentials."""
        return self._credentials

    def save(self, credentials: FirebaseCredentials) -> None:
        """Replace the held credentials."""
        self._credentials = credentials

    def clear(self) -> None:
        """Drop the held credentials."""
        self._credentials = None


class FileCredentialStore:
    """A :class:`CredentialStore` backed by a ``0600`` JSON file.

    Persistence is not an optimisation here: ``wake_alarm``'s PC side is a
    fresh process every minute and ``diet_guard``'s every 15 minutes, so an
    in-memory store would re-authenticate thousands of times a day.
    """

    def __init__(self, path: Path) -> None:
        """Store credentials at ``path``, creating parent dirs as needed."""
        self._path = path

    def load(self) -> FirebaseCredentials | None:
        """Return the stored credentials, or ``None`` if the file is absent.

        A corrupt or truncated file (an interrupted write) reads as "not
        signed in" rather than raising: the caller's next step is to sign in
        again, which repairs it.
        """
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        try:
            return FirebaseCredentials.from_json(data)
        except (KeyError, TypeError, ValueError):
            return None

    def save(self, credentials: FirebaseCredentials) -> None:
        """Write ``credentials`` atomically, readable only by this user."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._path.with_suffix(f"{self._path.suffix}.tmp")
        # Create with 0600 from the outset -- writing then chmod'ing would
        # leave the refresh token world-readable for the gap in between.
        temp.touch(mode=0o600)
        temp.write_text(json.dumps(credentials.to_json()), encoding="utf-8")
        temp.replace(self._path)

    def clear(self) -> None:
        """Delete the credentials file if it exists."""
        self._path.unlink(missing_ok=True)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


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
        body = self._post(
            f"{_REFRESH_BASE}/token?key={self._api_key}",
            {"grant_type": "refresh_token", "refresh_token": refresh_token},
            "refresh the session",
        )
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
        except requests.RequestException as exc:
            msg = f"network error trying to {what}"
            raise FirebaseAuthError(msg) from exc
        if not response.ok:
            reason = _reason(response)
            msg = f"failed to {what}: HTTP {response.status_code}{reason}"
            raise FirebaseAuthError(msg)
        return response.json()


def _reason(response: requests.Response) -> str:
    """Return Google's machine-readable error reason, in parentheses.

    Pulls ``INVALID_PASSWORD`` / ``TOKEN_EXPIRED`` / ``USER_DISABLED`` out of
    the body so the raised message says what actually went wrong rather than
    just reporting a status code.
    """
    try:
        data = response.json()
    except ValueError:
        # A non-JSON body (a proxy error page, say): the status code is all
        # the detail there is.
        return ""
    if not isinstance(data, dict):
        return ""
    error = data.get("error")
    if isinstance(error, dict):
        return f" ({error.get('message')})"
    if isinstance(error, str):
        return f" ({error})"
    return ""
