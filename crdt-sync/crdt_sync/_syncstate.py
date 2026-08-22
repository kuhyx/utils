"""Where a device records what it has already pushed and pulled.

Split from :mod:`crdt_sync._sync`, which keeps the sync itself. The state is
what makes a tick cheap: without it every run re-downloads every peer, and
with a stale one a device silently stops seeing updates. Two stores ship --
in-memory for tests, and a JSON file for real installs.

Re-exported from :mod:`crdt_sync._sync`, so existing imports keep working.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncState:
    """What one device remembers between ticks to skip needless traffic.

    Attributes:
    ----------
    pushed_rev:
        Hash of what this device last pushed, so an unchanged log is not
        re-uploaded. 88% of the pushes in the GitHub-backed history this
        replaces were byte-identical no-ops.
    peer_revs:
        The hash each peer had when we last downloaded it, so an unchanged
        peer is not re-downloaded.

    Notes:
    -----
    **Must be stored next to the log itself and cleared with it.** Skipping
    an unchanged peer is only sound because that peer's records are already
    merged into the local log; a cache that outlived its log would skip peers
    whose data had been lost.

    """

    pushed_rev: str | None = None
    peer_revs: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> dict[str, object]:
        """Return a JSON-serializable form."""
        return {"pushed_rev": self.pushed_rev, "peer_revs": self.peer_revs}

    @classmethod
    def from_json(cls, data: dict[str, object]) -> SyncState:
        """Rebuild state from :meth:`to_json` output, ignoring junk.

        A malformed cache degrades into "fetch everything" rather than
        raising: it is an optimisation, never a source of failure.
        """
        pushed = data.get("pushed_rev")
        peers = data.get("peer_revs")
        return cls(
            pushed_rev=pushed if isinstance(pushed, str) else None,
            peer_revs={
                key: value
                for key, value in (peers or {}).items()
                if isinstance(value, str)
            }
            if isinstance(peers, dict)
            else {},
        )


class SyncStateStore(Protocol):
    """Where :func:`sync_log` persists its :class:`SyncState` between runs."""

    def load(self) -> SyncState:
        """Return the stored state, or a default one."""

    def save(self, state: SyncState) -> None:
        """Persist ``state``."""


class MemorySyncStateStore:
    """A :class:`SyncStateStore` that forgets on exit, for tests.

    Correct but pessimistic: every process re-downloads every peer and
    re-pushes the local log, which is exactly the old behaviour.
    """

    def __init__(self) -> None:
        """Start with empty state."""
        self._state = SyncState()

    def load(self) -> SyncState:
        """Return the held state."""
        return self._state

    def save(self, state: SyncState) -> None:
        """Replace the held state."""
        self._state = state


class FileSyncStateStore:
    """A :class:`SyncStateStore` backed by a JSON file.

    Persistence is what makes the saving real for short-lived callers:
    ``wake_alarm``'s PC side is a fresh process every minute and
    ``diet_guard``'s every 15 minutes, so an in-memory store would save
    nothing at all.
    """

    def __init__(self, path: Path) -> None:
        """Keep state in the file at ``path``."""
        self._path = path

    def load(self) -> SyncState:
        """Return the stored state, or a default one if unreadable."""
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return SyncState()
        if not isinstance(data, dict):
            return SyncState()
        return SyncState.from_json(data)

    def save(self, state: SyncState) -> None:
        """Write ``state`` atomically, so a crash cannot truncate it."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._path.with_suffix(f"{self._path.suffix}.tmp")
        temp.write_text(json.dumps(state.to_json()), encoding="utf-8")
        temp.replace(self._path)
