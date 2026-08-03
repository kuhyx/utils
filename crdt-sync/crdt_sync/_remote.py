"""Backend-neutral remote-storage contract that sync talks through.

Deliberately tiny: :func:`crdt_sync.sync_log` and every app-level sync
service talk only to :class:`RemoteStore`, so swapping the storage backend
(GitHub Contents API, Firebase Realtime Database, a dual-writing mirror of
both) is a constructor change at the call site and nothing more.

Mirrors ``crdt_sync_dart``'s ``lib/src/remote_store.dart``; keep the two in
step.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class RemoteSyncError(Exception):
    """Raised for a remote-storage failure the caller must not ignore.

    The backend-neutral base of the error hierarchy: catch this to handle
    "the sync transport failed" regardless of which backend is configured.
    Backends narrow it -- :class:`crdt_sync.GitHubSyncError` and
    :class:`crdt_sync.FirebaseSyncError` both derive from it -- so existing
    ``except GitHubSyncError`` handlers keep working while a caller that has
    been migrated can catch the base type instead.
    """


class RemoteNotFoundError(RemoteSyncError):
    """Raised when the configured remote itself is unreachable.

    Distinguished from a missing *path* (nothing pushed there yet, which is
    benign -- it just means no other device has synced before) so the caller
    can tell "the repo/database is wrong or the credential isn't scoped to
    it" apart from "no other device has synced yet".
    """


@runtime_checkable
class RemoteStore(Protocol):
    """Dumb keyed storage of UTF-8 text blobs, with directory listing.

    Implementations raise :class:`RemoteSyncError` (or a subclass) for any
    failure the caller must not silently ignore, and treat a missing path as
    a benign ``None`` / empty list rather than an error.

    A ``Protocol`` rather than an ABC so the existing
    :class:`crdt_sync.GitHubSyncClient` satisfies it structurally, with no
    base class to add and no change to its own tests.
    """

    def list_directory(self, path: str) -> list[str]:
        """Return the entry names directly under ``path``.

        Returns an empty list when nothing has been written there yet.
        Includes both files and subdirectories: the
        ``<path_prefix>/<device_id>/<filename>`` layout needs to discover
        device *directories*, not just files.
        """

    def get_file_text(self, path: str) -> str | None:
        """Return the text stored at ``path``, or ``None`` if absent."""

    def put_file_text(self, path: str, text: str, *, message: str) -> None:
        """Create or replace the text at ``path``.

        ``message`` is a human-readable reason for the write. Backends that
        record one (GitHub commits) use it; backends that do not (Firebase)
        ignore it.
        """

    def delete_file(self, path: str, *, message: str = ...) -> None:
        """Delete ``path``. A no-op when ``path`` does not exist."""

    def can_access_remote(self) -> bool:
        """Return whether the configured credential can reach the remote.

        A lightweight connection test for a settings "Test connection"
        button: it probes the remote root, so it succeeds even before any
        file has been pushed. Never raises -- a network failure or missing
        remote returns ``False``.
        """
