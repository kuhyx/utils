# Copyright (c) 2026 Krzysztof Rudnicki
"""Every file this package owns, as one value that can be swapped wholesale.

Threading five separate ``*_path`` keyword arguments through the API was the
first shape of this, and it had a specific failure mode: a test suite has to
redirect *every* one of them, and a module that starts importing a sixth
silently keeps writing to real user state while the suite still looks green.
That has happened before in this fleet and cost a live log file.

One bundle means one seam. ``Paths.under(tmp_path)`` redirects everything at
once, and a new file added to this class is redirected by construction
rather than by remembering to update a list somewhere else.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from freedays._constants import (
    AUDIT_PATH,
    DEVICE_ID_PATH,
    HMAC_KEY_FILE,
    LOG_PATH,
    SYNC_STATE_PATH,
)

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class Paths:
    """Where the pool, the device id, the audit trail and sync state live."""

    log: Path
    device_id: Path
    audit: Path
    hmac_key: Path
    sync_state: Path

    @classmethod
    def default(cls) -> Paths:
        """The real, per-user locations under ``~/.local/share/freedays``."""
        return cls(
            log=LOG_PATH,
            device_id=DEVICE_ID_PATH,
            audit=AUDIT_PATH,
            hmac_key=HMAC_KEY_FILE,
            sync_state=SYNC_STATE_PATH,
        )

    @classmethod
    def under(cls, directory: Path) -> Paths:
        """Every file, relocated under ``directory``. The test seam."""
        return cls(
            log=directory / "free_days.json",
            device_id=directory / "device_id",
            audit=directory / "audit.jsonl",
            hmac_key=directory / "hmac.key",
            sync_state=directory / "sync_state.json",
        )


def resolve_paths(paths: Paths | None) -> Paths:
    """Return ``paths``, or the real locations when it is ``None``."""
    return paths if paths is not None else Paths.default()
