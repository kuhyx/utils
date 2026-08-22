"""The errors the Firebase sync backend raises.

Split from :mod:`crdt_sync._firebase` for the 250-line cap, mirroring
:mod:`crdt_sync._gherrors` on the GitHub side.

Re-exported from :mod:`crdt_sync._firebase`, so existing imports keep working.
"""

from __future__ import annotations

from crdt_sync._remote import RemoteNotFoundError, RemoteSyncError


class FirebaseSyncError(RemoteSyncError):
    """Raised for an RTDB failure the caller must not silently ignore."""


class DatabaseNotFoundError(FirebaseSyncError, RemoteNotFoundError):
    """Raised when the database is unreachable or the uid is not allowed.

    The Firebase counterpart of :class:`crdt_sync.RepoNotFoundError`: "the
    database URL is wrong, or the security rules reject this account", as
    opposed to "nothing has been pushed to that path yet", which is benign
    and surfaces as ``None``.
    """
