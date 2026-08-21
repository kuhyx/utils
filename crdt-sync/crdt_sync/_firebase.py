"""Firebase Realtime Database as dumb keyed storage, over its REST API.

The RTDB REST endpoints are plain HTTPS, so this works identically under
systemd, in a venv, and alongside the Dart client on Android -- and the two
write byte-identical payloads, so a device on either implementation reads the
other's.

Why RTDB rather than Firestore: on the Spark (free) plan RTDB bills only
storage and bandwidth, with **no per-operation quota**, so a misbehaving sync
loop can never exhaust a daily budget and silently stop working mid-day.

Mirrors ``crdt_sync_dart``'s ``lib/src/firebase_client.dart``; keep the two in
step.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import requests as _requests

from crdt_sync._http import new_session
from crdt_sync._remote import RemoteNotFoundError, RemoteSyncError

# Bound to the name ``requests`` so the call sites below -- and the tests
# that patch ``<module>.requests.<verb>`` -- are unchanged by pooling.
requests = new_session()


if TYPE_CHECKING:
    from crdt_sync._firebase_auth import FirebaseTokenProvider

_DEFAULT_TIMEOUT_SECONDS = 15
_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403

# Characters Realtime Database forbids in a key, plus ``~`` itself because it
# is this module's escape character. ``/`` is absent deliberately: it is the
# path separator, handled by splitting into segments before escaping.
_ESCAPES = {
    "~": "~7E",
    ".": "~2E",
    "$": "~24",
    "#": "~23",
    "[": "~5B",
    "]": "~5D",
}
_UNESCAPES = {escape: char for char, escape in _ESCAPES.items()}
_ESCAPE_LENGTH = 3


class FirebaseSyncError(RemoteSyncError):
    """Raised for an RTDB failure the caller must not silently ignore."""


class DatabaseNotFoundError(FirebaseSyncError, RemoteNotFoundError):
    """Raised when the database is unreachable or the uid is not allowed.

    The Firebase counterpart of :class:`crdt_sync.RepoNotFoundError`: "the
    database URL is wrong, or the security rules reject this account", as
    opposed to "nothing has been pushed to that path yet", which is benign
    and surfaces as ``None``.
    """


def encode_key(segment: str) -> str:
    """Escape one path segment into a legal Realtime Database key.

    RTDB rejects ``. $ # [ ] /`` in keys, and the REST API's trailing
    ``.json`` is a *format suffix* rather than part of the path -- so a
    filename like ``log.json`` cannot be stored verbatim. The mapping is a
    reversible ``~XX`` escape (``log.json`` -> ``log~2Ejson``) rather than a
    lossy "strip the extension", because callers see these names again:
    todo-app lists *filenames*, not device directories, and must keep getting
    ``<uuid>.json`` back.

    ``~`` is the escape character because it is legal in RTDB keys and
    unreserved in URLs, so the escaped form needs no percent-encoding --
    which the server would otherwise decode back into the illegal character.

    Parameters
    ----------
    segment : str
        One path segment, with no ``/`` in it.

    Returns:
    -------
    str
        The escaped key.

    """
    return "".join(_ESCAPES.get(char, char) for char in segment)


def decode_key(key: str) -> str:
    """Reverse :func:`encode_key`.

    Parameters
    ----------
    key : str
        An escaped Realtime Database key.

    Returns:
    -------
    str
        The original segment.

    """
    out: list[str] = []
    index = 0
    while index < len(key):
        escape = key[index : index + _ESCAPE_LENGTH]
        char = _UNESCAPES.get(escape)
        if char is None:
            out.append(key[index])
            index += 1
        else:
            out.append(char)
            index += _ESCAPE_LENGTH
    return "".join(out)


def encode_path(path: str) -> str:
    """Escape every segment of a ``/``-separated logical path.

    Parameters
    ----------
    path : str
        A logical path such as ``"todo-sync/notes/abc.json"``.

    Returns:
    -------
    str
        The path with each segment escaped, empty segments dropped.

    """
    return "/".join(encode_key(part) for part in path.split("/") if part)


class FirebaseSyncClient:
    """Realtime Database seen through the same contract as GitHub.

    Reads and writes UTF-8 text blobs stored as JSON string leaves, so the
    payload is byte-identical to what the GitHub backend stored and the two
    can be mirrored against each other during migration.
    """

    def __init__(
        self,
        database_url: str,
        auth: FirebaseTokenProvider,
        *,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Create a client for ``database_url`` authenticated by ``auth``.

        Args:
            database_url: The database's HTTPS origin.
            auth: Mints the ID token every request carries.
            timeout_seconds: Per-request network timeout.
        """
        self._database_url = database_url.rstrip("/")
        self.auth = auth
        self._timeout_seconds = timeout_seconds

    def _url(self, path: str) -> str:
        return f"{self._database_url}/{encode_path(path)}.json"

    def _params(self, **extra: str) -> dict[str, str]:
        return {"auth": self.auth.id_token(), **extra}

    def _raise(self, what: str, response: _requests.Response) -> None:
        """Raise the right error type for a non-2xx response.

        401/403 mean the rules rejected this uid or the token is bad.
        Everything else -- including a Spark quota exhaustion, which answers
        with an error rather than billing you -- is a plain
        :class:`FirebaseSyncError`. Nothing is ever swallowed: a
        quota-exhausted database that silently returned "no data" would look
        exactly like "nothing to sync".
        """
        detail = response.text.strip()
        if response.status_code in (_HTTP_UNAUTHORIZED, _HTTP_FORBIDDEN):
            msg = (
                f"{what} rejected: HTTP {response.status_code} {detail} -- "
                f"the database URL or the security rules do not allow this "
                f"account"
            )
            raise DatabaseNotFoundError(msg)
        msg = f"{what} failed: HTTP {response.status_code} {detail}"
        raise FirebaseSyncError(msg)

    def _get(self, path: str, **params: str) -> _requests.Response:
        try:
            return requests.get(
                self._url(path),
                params=self._params(**params),
                timeout=self._timeout_seconds,
            )
        except _requests.RequestException as exc:
            msg = f"network error reading {path}"
            raise FirebaseSyncError(msg) from exc

    def list_directory(self, path: str) -> list[str]:
        """Return the entry names directly under ``path``.

        Uses ``shallow=true``, which returns ``{key: true}`` without any
        values -- so a listing costs bytes rather than the whole subtree.
        That is the difference between a sync tick costing hundreds of bytes
        and hundreds of kilobytes.

        Raises:
            DatabaseNotFoundError: If the rules reject this account.
            FirebaseSyncError: For any other non-2xx response or network
                error.
        """
        response = self._get(path, shallow="true")
        if not response.ok:
            self._raise(f"listing {path}", response)
        data = response.json()
        if not isinstance(data, dict):
            return []
        return [decode_key(key) for key in data]

    def get_file_text(self, path: str) -> str | None:
        """Return the text stored at ``path``, or ``None`` if absent.

        Raises:
            DatabaseNotFoundError: If the rules reject this account.
            FirebaseSyncError: If the value is not a text blob, or for any
                other non-2xx response or network error.
        """
        response = self._get(path)
        if not response.ok:
            self._raise(f"reading {path}", response)
        data = response.json()
        if data is None:
            return None
        if not isinstance(data, str):
            msg = (
                f"value at {path} is {type(data).__name__}, not the expected text blob"
            )
            raise FirebaseSyncError(msg)
        return data

    def put_file_text(self, path: str, text: str, *, message: str) -> None:
        """Write ``text`` at ``path``.

        Args:
            path: A logical path such as ``"ns/devices/pc/log.json"``.
            text: The full new content.
            message: Ignored -- RTDB has no commit log to attach a reason to.
                Present so this matches the ``RemoteStore`` contract.

        Raises:
            FirebaseSyncError: On any non-2xx response or network error.
        """
        del message
        try:
            response = requests.put(
                self._url(path),
                params=self._params(),
                json=text,
                timeout=self._timeout_seconds,
            )
        except _requests.RequestException as exc:
            msg = f"network error writing {path}"
            raise FirebaseSyncError(msg) from exc
        if not response.ok:
            self._raise(f"writing {path}", response)

    def get_string_map(self, path: str) -> dict[str, str]:
        """Return the map at ``path`` as ``key -> text``, empty if absent.

        Tolerates a non-map or malformed value rather than raising: this
        backs the revision cache, which is an *optimisation*. A corrupt revs
        node must degrade into "fetch everything", never into a failed sync.

        Raises:
            FirebaseSyncError: Only for a transport-level failure.
        """
        response = self._get(path)
        if not response.ok:
            self._raise(f"reading {path}", response)
        data = response.json()
        if not isinstance(data, dict):
            return {}
        return {
            decode_key(key): value
            for key, value in data.items()
            if isinstance(value, str)
        }

    def delete_file(self, path: str, *, message: str = "crdt_sync: delete") -> None:
        """Delete ``path``. A no-op if it does not exist.

        Args:
            path: A logical path.
            message: Ignored, as for :meth:`put_file_text`.

        Raises:
            FirebaseSyncError: On any non-2xx response or network error.
        """
        del message
        try:
            response = requests.delete(
                self._url(path),
                params=self._params(),
                timeout=self._timeout_seconds,
            )
        except _requests.RequestException as exc:
            msg = f"network error deleting {path}"
            raise FirebaseSyncError(msg) from exc
        if not response.ok:
            self._raise(f"deleting {path}", response)

    def can_access_remote(self) -> bool:
        """Return whether the credential can reach the database.

        Never raises -- a bad URL, a rejected token, a missing session or a
        network failure all report ``False``, so a settings "Test connection"
        button cannot blow up.
        """
        try:
            response = requests.get(
                self._url(""),
                params=self._params(shallow="true"),
                timeout=self._timeout_seconds,
            )
        except _requests.RequestException:
            return False
        except RemoteSyncError:
            # Includes FirebaseAuthError: "cannot get a token" is exactly
            # "cannot access the remote".
            return False
        return response.ok
