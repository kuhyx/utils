"""Downloading peers' logs, skipping the ones we already have.

Split from :mod:`crdt_sync._sync`, which keeps the push half and the
orchestration. The revision map is the optimisation that makes a tick cheap:
a peer whose published revision matches what we last merged is not fetched at
all, so a quiet device costs one small read instead of one read per peer.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from crdt_sync._log import Log
    from crdt_sync._remote import RemoteStore

from crdt_sync._revisions import revision_of
from crdt_sync._syncstate import SyncState

_logger = logging.getLogger(__name__)


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
