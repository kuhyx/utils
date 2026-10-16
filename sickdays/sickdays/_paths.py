# Copyright (c) 2026 Krzysztof Rudnicki
"""Every file this package owns, as one value that can be swapped wholesale.

The same seam freedays uses: one bundle, so ``Paths.under(tmp_path)``
redirects everything at once and a file added to this class later is
redirected by construction rather than by remembering to update a list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sickdays._constants import (
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
        """The real, per-user locations under ``~/.local/share/sickdays``."""
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
            log=directory / "sick_days.json",
            device_id=directory / "device_id",
            audit=directory / "audit.jsonl",
            hmac_key=directory / "hmac.key",
            sync_state=directory / "sync_state.json",
        )


def resolve_paths(paths: Paths | None) -> Paths:
    """Return ``paths``, or the real locations when it is ``None``."""
    return paths if paths is not None else Paths.default()
