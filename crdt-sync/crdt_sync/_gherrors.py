"""The errors the GitHub sync backend raises.

Split from :mod:`crdt_sync._github` for the 250-line cap. Kept separate so a
caller can catch them without importing the client -- and so the client file
is the client, not its taxonomy.

Re-exported from :mod:`crdt_sync._github`, so existing imports keep working.
"""

from __future__ import annotations

from crdt_sync._remote import RemoteNotFoundError, RemoteSyncError


class GitHubSyncError(RemoteSyncError):
    """Raised for a GitHub API failure the caller must not silently ignore."""


class RepoNotFoundError(GitHubSyncError, RemoteNotFoundError):
    """Raised when the configured repo itself is unreachable.

    Distinguished from a path-404 (nothing pushed to that path yet, which is
    benign -- it just means no other device has synced before) so the caller
    can tell "the repo name is wrong or the token isn't scoped to it" apart
    from "no other device has synced yet".

    Derives from both so existing ``except GitHubSyncError`` handlers still
    cover it *and* backend-neutral callers can catch "the remote itself is
    missing" without naming GitHub.
    """
