"""The three argument bundles :func:`crdt_sync.sync_log` takes.

Split from :mod:`crdt_sync._sync` for the 250-line cap. Grouping sync_log's
arguments into what/how/whether bundles is what keeps its signature readable;
the bundles themselves carry no behaviour.

Re-exported from :mod:`crdt_sync._sync`, so existing imports keep working.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from crdt_sync._log import Log
    from crdt_sync._remote import RemoteStore
    from crdt_sync._syncstate import SyncStateStore


_DEFAULT_FILENAME = "log.json"


@dataclass(frozen=True)
class SyncTarget:
    """Which remote, which device, and where its logs live.

    Args:
        client: An authenticated :class:`RemoteStore` -- a
            :class:`crdt_sync.GitHubSyncClient`, a
            :class:`crdt_sync.FirebaseSyncClient`, or a mirror of both.
        device_id: This device's identifier; also the directory name its own
            log is pushed under.
        path_prefix: The directory holding one subdirectory per device
            (e.g. ``"devices"``).
        legacy_device_id: The id this device pushed under before migrating to
            a persisted uuid. Treated as this device's own for skip-own
            purposes, so its pre-migration log is not pulled back and
            re-merged as a peer's. Pass ``None`` once the old path has been
            reclaimed.
    """

    client: RemoteStore
    device_id: str
    path_prefix: str
    legacy_device_id: str | None = None

    @property
    def own_ids(self) -> frozenset[str]:
        """Every id whose pushed log belongs to this device."""
        if self.legacy_device_id is None:
            return frozenset({self.device_id})
        return frozenset({self.device_id, self.legacy_device_id})


@dataclass(frozen=True)
class LogCodec:
    """How a log is turned into pushed text and back.

    Args:
        encode: Serializes a merged log for pushing.
        decode: Parses a remote device's pushed text back into a log.
            Raising ``ValueError``, ``KeyError``, or ``TypeError`` is treated
            as a corrupt/unparsable push, and that device is skipped for
            this tick rather than aborting the whole sync.
        filename: The file name each device pushes its log as.
        commit_message: The commit message used for this device's push.
    """

    encode: Callable[[Log], str]
    decode: Callable[[str], Log]
    filename: str = _DEFAULT_FILENAME
    commit_message: str = "crdt_sync: update log"


@dataclass(frozen=True)
class RevisionTracking:
    """Optional skip-unchanged behaviour for a tick.

    Omit it entirely and the tick behaves exactly as it always did: fetch
    everything, push unconditionally.

    Args:
        state_store: Persists what this device last pushed and last merged.
        revs_path: Where revisions live; defaults to
            :func:`default_revs_path`.
    """

    state_store: SyncStateStore | None = None
    revs_path: str | None = None
