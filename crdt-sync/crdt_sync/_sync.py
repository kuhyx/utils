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

_logger = logging.getLogger(__name__)

_DEFAULT_FILENAME = "log.json"


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


def revision_of(encoded_log: str) -> str:
    """Return the revision of a serialized log: a content hash.

    A hash rather than the log's maximum HLC because merging a peer's *older*
    record changes the content without raising the maximum -- with three
    devices in one namespace (diet-guard has ``pc``, ``phone`` and
    ``desktop``) a clock-based revision can miss a peer's merged state. It is
    also the same value used to suppress no-op pushes, so the two
    optimisations share one mechanism.

    Parameters
    ----------
    encoded_log : str
        The serialized log, exactly as it would be pushed.

    Returns:
    -------
    str
        A hex SHA-256 digest.

    """
    return hashlib.sha256(encoded_log.encode("utf-8")).hexdigest()


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


def _remote_revs(client: RemoteStore, revs_path: str) -> dict[str, str]:
    """Return every peer's published revision, cheaply where possible.

    Degrades to an empty map -- meaning "fetch everything", the old behaviour
    -- on any backend without a bulk-map read, so correctness never depends
    on the optimisation being available.
    """
    get_string_map = getattr(client, "get_string_map", None)
    if get_string_map is None:
        return {}
    return get_string_map(revs_path)


@dataclass(frozen=True)
class _PullContext:
    """Everything :func:`_pull_remote_logs` needs for one tick's pull.

    A bundle rather than eight positional parameters: they are always passed
    together, from one call site, and several share a type -- exactly the
    shape where a positional mix-up is silent.
    """

    client: RemoteStore
    own_ids: frozenset[str]
    path_prefix: str
    filename: str
    decode: Callable[[str], Log]
    remote_revs: dict[str, str]
    state: SyncState


def _pull_remote_logs(
    ctx: _PullContext,
    seen_revs: dict[str, str],
) -> list[Log]:
    """Return every other device's last-pushed log, skipping this one.

    A device whose pushed file is corrupt or unparsable (e.g. an interrupted
    push) is logged and skipped, same as one that has never pushed at all --
    the remote is an external system boundary, and one bad device's file must
    not stall merging in every other device's.

    ``own_ids`` is a *set* rather than a single id because a device that has
    migrated from a role constant to a persisted uuid still owns the log it
    pushed under the old id. Matching only the current id would pull that
    file back and re-merge this device's own pre-migration history as though
    a peer had written it -- idempotent, but pure wasted transfer.

    Records into ``seen_revs`` which peers are now merged in, so the next
    tick can skip them.
    """
    remote_logs: list[Log] = []
    for other_device_id in ctx.client.list_directory(ctx.path_prefix):
        if other_device_id in ctx.own_ids:
            continue
        remote_rev = ctx.remote_revs.get(other_device_id)
        if remote_rev is not None and remote_rev == ctx.state.peer_revs.get(
            other_device_id
        ):
            # Unchanged since we last merged it, and that merge is already
            # part of local_log -- so the (potentially hundreds of KB)
            # download is pure waste. Carry the revision forward so it stays
            # skipped next tick.
            seen_revs[other_device_id] = remote_rev
            continue
        text = ctx.client.get_file_text(
            f"{ctx.path_prefix}/{other_device_id}/{ctx.filename}"
        )
        if text is None:
            continue
        try:
            remote_logs.append(ctx.decode(text))
        except (ValueError, KeyError, TypeError):
            _logger.warning(
                "Unparsable log pushed by device %r, skipping",
                other_device_id,
            )
            # Deliberately not recorded as seen: a corrupt push must be
            # retried next tick, not remembered as merged.
            continue
        seen_revs[other_device_id] = remote_rev or revision_of(text)
    return remote_logs


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
