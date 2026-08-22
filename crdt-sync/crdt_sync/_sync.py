"""Domain-agnostic pull/merge/push sync orchestration.

Generalizes diet_guard's original ``_sync.py`` (pull every other device's
pushed log, merge with the local one, push this device's own merged result
back up) so any app can reuse the loop while keeping its own on-disk JSON
shape via the ``encode``/``decode`` callbacks -- this module has no opinion
on what a ``Record``'s fields actually mean.

Mirrors ``crdt_sync_dart``'s ``lib/src/sync.dart``; keep the two in step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import logging
from typing import TYPE_CHECKING, Protocol

from crdt_sync._log import merge_logs

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from crdt_sync._log import Log
    from crdt_sync._remote import RemoteStore

from crdt_sync._pull import _PullContext, _pull_remote_logs, _remote_revs
from crdt_sync._revisions import revision_of
from crdt_sync._syncstate import (
    FileSyncStateStore,
    MemorySyncStateStore,
    SyncState,
    SyncStateStore,
)

_logger = logging.getLogger(__name__)

_DEFAULT_FILENAME = "log.json"


def default_revs_path(path_prefix: str) -> str:
    """Return where revisions live for ``path_prefix``.

    A ``revs`` sibling of the device directory, e.g.
    ``diet-guard-sync/devices`` -> ``diet-guard-sync/revs`` and
    ``todo-sync/notes`` -> ``todo-sync/revs``.

    Parameters
    ----------
    path_prefix : str
        The directory holding one subdirectory per device.

    Returns:
    -------
    str
        The revisions directory.

    """
    head, separator, _ = path_prefix.rpartition("/")
    return f"{head}/revs" if separator else f"{path_prefix}/revs"


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


def sync_log(
    target: SyncTarget,
    local_log: Log,
    codec: LogCodec,
    revisions: RevisionTracking | None = None,
) -> Log:
    """Run one full sync tick: pull every other device's log, merge, push.

    Pulls from ``<path_prefix>/<other-device-id>/<filename>`` for every
    device directory the remote reports under ``path_prefix``, merges each
    into ``local_log`` with :func:`crdt_sync.merge_logs`, then pushes this
    device's own merged result to ``<path_prefix>/<device_id>/<filename>``.

    Args:
        target: Which remote and device this tick is for.
        local_log: This device's current full log (including tombstones).
        codec: How to serialize and parse a log.
        revisions: Pass one to skip downloading peers that have not changed
            and skip pushing a log that has not changed. ``None`` fetches
            everything and pushes unconditionally.

    Returns:
        The merged log, as pushed.

    Notes:
        Revisions live at ``<revs_path>/<device_id>`` -- one small text node
        per device, each written only by its owner. Deliberately *not* one
        shared map per namespace: a whole-map write would erase every other
        device's entry, after which those peers would look permanently
        unchanged and never be fetched again. Per-device keys make that
        failure impossible rather than merely avoided.
    """
    tracking = revisions if revisions is not None else RevisionTracking()
    state_store = tracking.state_store
    revs = (
        tracking.revs_path
        if tracking.revs_path is not None
        else default_revs_path(target.path_prefix)
    )
    state = state_store.load() if state_store is not None else SyncState()
    remote_revs = _remote_revs(target.client, revs) if state_store is not None else {}

    seen_revs: dict[str, str] = {}
    merged = _merge_peers(
        _PullContext(
            client=target.client,
            own_ids=target.own_ids,
            path_prefix=target.path_prefix,
            filename=codec.filename,
            decode=codec.decode,
            remote_revs=remote_revs,
            state=state,
        ),
        local_log,
        seen_revs,
    )

    encoded = codec.encode(merged)
    revision = revision_of(encoded)
    if not (state_store is not None and revision == state.pushed_rev):
        _push(
            target,
            codec,
            encoded,
            _RevisionMarker(revs, revision) if state_store is not None else None,
        )
    if state_store is not None:
        state_store.save(SyncState(pushed_rev=revision, peer_revs=seen_revs))
    return merged


def _merge_peers(
    ctx: _PullContext,
    local_log: Log,
    seen_revs: dict[str, str],
) -> Log:
    """Return ``local_log`` with every peer's pushed log merged in."""
    merged = dict(local_log)
    for remote_log in _pull_remote_logs(ctx, seen_revs):
        merged = merge_logs(merged, remote_log)
    return merged


@dataclass(frozen=True)
class _RevisionMarker:
    """The revision node a tracked push publishes after its log."""

    revs_path: str
    revision: str


def _push(
    target: SyncTarget,
    codec: LogCodec,
    encoded: str,
    marker: _RevisionMarker | None,
) -> None:
    """Push this device's merged log, then its revision marker."""
    target.client.put_file_text(
        f"{target.path_prefix}/{target.device_id}/{codec.filename}",
        encoded,
        message=codec.commit_message,
    )
    if marker is not None:
        # Published after the log, never before: a peer that cached
        # "seen rev X" against a log it never received would skip it
        # forever.
        target.client.put_file_text(
            f"{marker.revs_path}/{target.device_id}",
            marker.revision,
            message=codec.commit_message,
        )
