"""Minimal GitHub Contents API client used as dumb file storage.

GitHub is used purely as file storage via the REST Contents API, not a git
clone -- there is no working tree and no git-level merge; the only merge is
the domain-level one in :mod:`crdt_sync._log`. Extracted from diet_guard's
``_sync_github.py`` (itself ported in spirit from ``todo``'s sync
transport), generalized to be domain-agnostic.
"""

from __future__ import annotations

import base64

import requests as _requests

from crdt_sync._http import new_session
from crdt_sync._remote import RemoteNotFoundError, RemoteSyncError

# Bound to the name ``requests`` so the call sites below -- and the tests
# that patch ``<module>.requests.<verb>`` -- are unchanged by pooling.
requests = new_session()


_API_BASE = "https://api.github.com"
_HTTP_NOT_FOUND = 404
_DEFAULT_TIMEOUT_SECONDS = 15


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


class GitHubSyncClient:
    """Thin wrapper around the subset of the Contents API sync needs."""

    def __init__(
        self,
        owner: str,
        repo: str,
        token: str,
        *,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Create a client scoped to one repo, authenticated with ``token``.

        Args:
            owner: The repo owner/org (e.g. ``"kuhyx"``).
            repo: The repo name (e.g. ``"my-app-sync"``).
            token: A GitHub PAT with contents read/write on that repo.
            timeout_seconds: Per-request network timeout.
        """
        self._owner = owner
        self._repo = repo
        self._timeout_seconds = timeout_seconds
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

    def _contents_url(self, path: str) -> str:
        return f"{_API_BASE}/repos/{self._owner}/{self._repo}/contents/{path}"

    def _get(self, path: str) -> _requests.Response:
        try:
            return requests.get(
                self._contents_url(path),
                headers=self._headers,
                timeout=self._timeout_seconds,
            )
        except _requests.RequestException as exc:
            msg = f"network error reading {path}"
            raise GitHubSyncError(msg) from exc

    def _repo_exists(self) -> bool:
        try:
            response = requests.get(
                f"{_API_BASE}/repos/{self._owner}/{self._repo}",
                headers=self._headers,
                timeout=self._timeout_seconds,
            )
        except _requests.RequestException:
            return False
        return response.ok

    def _raise_for_missing_path(self, path: str) -> None:
        """Raise :class:`RepoNotFoundError` only if the repo is unreachable.

        A 404 on a path within a reachable repo just means nothing has been
        pushed there yet, which is not an error worth raising on.
        """
        if not self._repo_exists():
            msg = (
                f"{self._owner}/{self._repo} not found, private without "
                f"access, or the token lacks contents permission "
                f"(while reading {path})"
            )
            raise RepoNotFoundError(msg)

    def get_file_text(self, path: str) -> str | None:
        """Return the decoded text content at ``path``, or None if unused.

        Args:
            path: A repo-relative file path, e.g. ``"devices/pc/log.json"``.

        Returns:
            The file's text content, or None if nothing has been pushed
            there yet (but the repo itself is reachable).

        Raises:
            RepoNotFoundError: If the repo itself is unreachable.
            GitHubSyncError: For any other non-2xx response or network error.
        """
        response = self._get(path)
        if response.status_code == _HTTP_NOT_FOUND:
            self._raise_for_missing_path(path)
            return None
        if not response.ok:
            msg = f"GET {path} failed: {response.status_code}"
            raise GitHubSyncError(msg)
        data = response.json()
        content = data.get("content", "") if isinstance(data, dict) else ""
        return base64.b64decode(content).decode("utf-8")

    def _existing_sha(self, path: str) -> str | None:
        response = self._get(path)
        if response.status_code == _HTTP_NOT_FOUND:
            self._raise_for_missing_path(path)
            return None
        if not response.ok:
            msg = f"GET {path} (for sha) failed: {response.status_code}"
            raise GitHubSyncError(msg)
        data = response.json()
        sha = data.get("sha") if isinstance(data, dict) else None
        return sha if isinstance(sha, str) else None

    def put_file_text(self, path: str, text: str, *, message: str) -> None:
        """Create or update the file at ``path`` with ``text``.

        Args:
            path: A repo-relative file path.
            text: The full new content (this device's complete merged log).
            message: The commit message for this push.

        Raises:
            GitHubSyncError: On any non-2xx response or network error.
        """
        sha = self._existing_sha(path)
        payload: dict[str, object] = {
            "message": message,
            "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        }
        if sha is not None:
            payload["sha"] = sha
        try:
            response = requests.put(
                self._contents_url(path),
                headers=self._headers,
                json=payload,
                timeout=self._timeout_seconds,
            )
        except _requests.RequestException as exc:
            msg = f"network error pushing {path}"
            raise GitHubSyncError(msg) from exc
        if not response.ok:
            msg = f"PUT {path} failed: {response.status_code}"
            raise GitHubSyncError(msg)

    def list_directory(self, path: str) -> list[str]:
        """Return the entry names directly under ``path`` (empty if unused).

        Args:
            path: A repo-relative directory path, e.g. ``"devices"``.

        Raises:
            RepoNotFoundError: If the repo itself is unreachable.
            GitHubSyncError: For any other non-2xx response or network error.
        """
        response = self._get(path)
        if response.status_code == _HTTP_NOT_FOUND:
            self._raise_for_missing_path(path)
            return []
        if not response.ok:
            msg = f"GET {path} (list) failed: {response.status_code}"
            raise GitHubSyncError(msg)
        data = response.json()
        if not isinstance(data, list):
            return []
        return [
            item["name"]
            for item in data
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]

    def can_access_repo(self) -> bool:
        """Return whether the token can read this repo (a connection test).

        Hits the bare repo endpoint, so it succeeds even before any file has
        been pushed. Never raises -- a network failure or missing repo is
        reported as ``False``.

        The GitHub-era name for :meth:`can_access_remote`; kept because app
        settings screens call it. Both do the same probe.
        """
        return self._repo_exists()

    def can_access_remote(self) -> bool:
        """Return whether the token can reach the remote (a connection test).

        The :class:`crdt_sync.RemoteStore` spelling of
        :meth:`can_access_repo`.
        """
        return self._repo_exists()

    def delete_file(self, path: str, *, message: str = "crdt_sync: delete") -> None:
        """Delete the file at ``path``, resolving its current sha itself.

        A no-op if ``path`` does not exist, so a repeated cleanup is safe.

        Args:
            path: A repo-relative file path.
            message: The commit message for the deletion.

        Raises:
            GitHubSyncError: On any non-2xx response or network error.
        """
        sha = self._existing_sha(path)
        if sha is None:
            return
        try:
            response = requests.delete(
                self._contents_url(path),
                headers=self._headers,
                json={"message": message, "sha": sha},
                timeout=self._timeout_seconds,
            )
        except _requests.RequestException as exc:
            msg = f"network error deleting {path}"
            raise GitHubSyncError(msg) from exc
        if not response.ok:
            msg = f"DELETE {path} failed: {response.status_code}"
            raise GitHubSyncError(msg)
