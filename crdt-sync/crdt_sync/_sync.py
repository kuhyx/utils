"""Domain-agnostic pull/merge/push sync orchestration.

Generalizes diet_guard's original ``_sync.py`` (pull every other device's
pushed log, merge with the local one, push this device's own merged result
back up) so any app can reuse the loop while keeping its own on-disk JSON
shape via the ``encode``/``decode`` callbacks -- this module has no opinion
on what a ``Record``'s fields actually mean.

Mirrors ``crdt_sync_dart``'s ``lib/src/sync.dart``; keep the two in step.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from crdt_sync._log import merge_logs

if TYPE_CHECKING:
    from crdt_sync._log import Log

from crdt_sync._pull import _pull_remote_logs, _PullContext, _remote_revs
from crdt_sync._revisions import revision_of
from crdt_sync._syncargs import LogCodec, RevisionTracking, SyncTarget
from crdt_sync._syncstate import (
    FileSyncStateStore,
    MemorySyncStateStore,
    SyncState,
    SyncStateStore,
)

# Named explicitly so the autofixer cannot prune an import that exists for its
# re-export: crdt_sync/__init__.py imports all of these from here.
__all__ = [
    "FileSyncStateStore",
    "LogCodec",
    "MemorySyncStateStore",
    "RevisionTracking",
    "SyncState",
    "SyncStateStore",
    "SyncTarget",
    "default_revs_path",
    "revision_of",
    "sync_log",
]

_logger = logging.getLogger(__name__)


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
