"""Firebase credentials and the stores that persist them.

Split from :mod:`crdt_sync._firebase_auth`, which keeps the token provider.
A credential set is an ID token, a refresh token and an expiry; the stores
decide where it survives a restart -- memory for tests, a mode-0600 file for
real installs.

Re-exported from :mod:`crdt_sync._firebase_auth`, so existing imports work.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import json
import logging
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

# Refresh this long before the token actually expires. An ID token lives ~1h;
# refreshing early means a tick that starts just under the wire still finishes
# with a valid token rather than 401ing halfway through a multi-file push.
_REFRESH_SKEW = dt.timedelta(minutes=5)


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
        except OSError, ValueError:
            return None
        try:
            return FirebaseCredentials.from_json(data)
        except KeyError, TypeError, ValueError:
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
