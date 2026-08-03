"""One-shot migration of the GitHub-backed sync repo into Firebase RTDB.

Reads through the GitHub API rather than a local clone: a checkout goes stale
the moment any device syncs, and seeding Firebase from stale data would
silently roll back whatever changed in between.

Writes through the real :class:`crdt_sync.FirebaseSyncClient`, so the
migration exercises the same key escaping and error handling the apps will,
then reads every blob back and compares bytes before reporting success.

Usage::

    python3 tool/migrate_github_to_firebase.py --dry-run
    python3 tool/migrate_github_to_firebase.py

Configuration comes from ``~/.config/crdt-sync/firebase.json`` and the GitHub
token from ``~/.config/diet_guard/sync_token``.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import sys

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from crdt_sync import (
    FirebaseSyncClient,
    FirebaseTokenProvider,
    MemoryCredentialStore,
)

_CONFIG_DIR = Path.home() / ".config" / "crdt-sync"
_GITHUB_TOKEN_FILE = Path.home() / ".config" / "diet_guard" / "sync_token"
_REPO = "kuhyx/syncs"
_API = "https://api.github.com"
_TIMEOUT_SECONDS = 30

# A migration that reports nothing is indistinguishable from one that did
# nothing, so progress goes to stdout -- via logging rather than print, which
# this project's lint config reserves for accidental debug output.
_logger = logging.getLogger("migrate")

# Paths deliberately left behind, each for a reason that would otherwise cost
# egress or storage forever. They stay in the GitHub repo, which is archived
# rather than deleted, so nothing is destroyed by skipping them.
_SKIP_PREFIXES = (
    # Pre-migration sqlite_crdt format, last written 2026-07-17. Nothing
    # reads it; `sync_service.dart` only touches `notes/`.
    "todo-sync/changesets/",
    # A replica that stopped syncing 2026-07-22: verified to hold 0 records,
    # 0 tombstones and 0 newer fields that `pc` and `phone` lack. Carrying it
    # over would cost a full re-download every tick forever, because a device
    # that publishes no revision can never be skipped.
    "diet-guard-sync/devices/desktop/",
)

# Not sync data -- documentation and directory placeholders.
_SKIP_NAMES = ("README.md", ".gitkeep")


@dataclass(frozen=True)
class Blob:
    """One file in the sync repo, with its exact bytes."""

    path: str
    text: str

    @property
    def size(self) -> int:
        """Return the payload size in bytes."""
        return len(self.text.encode("utf-8"))


def _github_session(token: str) -> requests.Session:
    """Return a session that retries transient failures.

    GitHub drops keep-alive connections routinely, and a migration that gave
    up half-way would leave Firebase holding a partial copy -- the one
    outcome worse than not starting. Retries cover connection resets and 5xx,
    plus 403/429 for secondary rate limiting.
    """
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }
    )
    retry = Retry(
        total=5,
        backoff_factor=1.0,
        status_forcelist=(403, 429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def _list_blobs(session: requests.Session) -> list[tuple[str, str]]:
    """Return ``(path, sha)`` for every file, via one recursive tree call."""
    response = session.get(
        f"{_API}/repos/{_REPO}/git/trees/HEAD",
        params={"recursive": "1"},
        timeout=_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    tree = response.json()
    if tree.get("truncated"):
        # Would silently migrate only part of the repo.
        msg = "GitHub truncated the tree listing; the repo is too large"
        raise RuntimeError(msg)
    return [
        (item["path"], item["sha"]) for item in tree["tree"] if item["type"] == "blob"
    ]


def _fetch_blob(session: requests.Session, path: str, sha: str) -> Blob:
    """Return the exact bytes of one blob.

    Uses the blobs API rather than the contents API: it is addressed by sha,
    so it cannot race a concurrent push into returning a different file than
    the tree listing described.
    """
    response = session.get(
        f"{_API}/repos/{_REPO}/git/blobs/{sha}", timeout=_TIMEOUT_SECONDS
    )
    response.raise_for_status()
    payload = response.json()
    raw = base64.b64decode(payload["content"])
    return Blob(path=path, text=raw.decode("utf-8"))


def _should_migrate(path: str) -> bool:
    if any(path.startswith(prefix) for prefix in _SKIP_PREFIXES):
        return False
    return Path(path).name not in _SKIP_NAMES


def _firebase_client() -> FirebaseSyncClient:
    config = json.loads((_CONFIG_DIR / "firebase.json").read_text())
    password = (_CONFIG_DIR / "password").read_text()
    auth = FirebaseTokenProvider(config["apiKey"], MemoryCredentialStore())
    auth.sign_in(config["email"], password)
    return FirebaseSyncClient(config["databaseUrl"], auth)


def _report(blobs: list[Blob], skipped: list[str]) -> None:
    """Log exactly what will move and what will not, before anything moves."""
    total = sum(blob.size for blob in blobs)
    _logger.info("%d files to migrate, %d bytes total", len(blobs), total)
    for blob in sorted(blobs, key=lambda b: -b.size):
        _logger.info("  %8d  %s", blob.size, blob.path)
    if skipped:
        _logger.info("%d skipped (see _SKIP_PREFIXES for why):", len(skipped))
        for path in skipped:
            _logger.info("            %s", path)


def main() -> int:
    """Run the migration, returning a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list what would be migrated, write nothing",
    )
    args = parser.parse_args()
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")

    session = _github_session(_GITHUB_TOKEN_FILE.read_text().strip())
    entries = _list_blobs(session)
    blobs = [
        _fetch_blob(session, path, sha)
        for path, sha in entries
        if _should_migrate(path)
    ]
    skipped = [path for path, _ in entries if not _should_migrate(path)]
    _report(blobs, skipped)

    if args.dry_run:
        _logger.info("DRY RUN -- nothing written")
        return 0

    client = _firebase_client()
    _logger.info("writing...")
    for blob in blobs:
        client.put_file_text(blob.path, blob.text, message="migration")

    # Verify by reading back through the same client: a migration that
    # reported success without checking would be indistinguishable from one
    # that silently dropped a file.
    _logger.info("verifying byte-for-byte...")
    mismatches = [
        blob.path for blob in blobs if client.get_file_text(blob.path) != blob.text
    ]
    if mismatches:
        _logger.error("FAILED -- %d file(s) did not round-trip:", len(mismatches))
        for path in mismatches:
            _logger.error("  %s", path)
        return 1

    _logger.info("OK -- %d files migrated and verified byte-for-byte", len(blobs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
