# Copyright (c) 2026 Krzysztof Rudnicki
"""On-disk E2E state for short-lived daemons (one process per tick).

The derived key is cached ``0600`` beside the app's other state, so Argon2id
runs once per machine rather than once a minute; it is no more sensitive
than ``~/.config/crdt-sync/password``, which it is derived from. The copy
memo records the old prefix's revisions last copied, so an unchanged old
prefix is not re-scanned every tick.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_MASTER = 32


def _slug(old_prefix: str) -> str:
    return hashlib.sha256(old_prefix.encode()).hexdigest()[:16]


def read_cached_key(state_dir: Path, old_prefix: str) -> bytes | None:
    """Return the cached 32-byte master key, or None."""
    path = state_dir / f"e2e-{_slug(old_prefix)}.key"
    if not path.exists():
        return None
    try:
        master = bytes.fromhex(path.read_text(encoding="utf-8").strip())
    except ValueError:
        return None
    return master if len(master) == _MASTER else None


def write_cached_key(state_dir: Path, old_prefix: str, master: bytes) -> None:
    """Store the master key owner-only."""
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / f"e2e-{_slug(old_prefix)}.key"
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_text(master.hex(), encoding="utf-8")


def read_copy_memo(state_dir: Path, old_prefix: str) -> str | None:
    """Return the old-prefix fingerprint last copied, or None."""
    path = state_dir / f"e2e-{_slug(old_prefix)}.copied"
    return path.read_text(encoding="utf-8") if path.exists() else None


def write_copy_memo(state_dir: Path, old_prefix: str, fingerprint: str) -> None:
    """Record that the old prefix was copied at ``fingerprint``."""
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / f"e2e-{_slug(old_prefix)}.copied"
    path.write_text(fingerprint, encoding="utf-8")
