"""Log: a collection of Records keyed by id, with a union-merge."""

from __future__ import annotations

from crdt_sync._record import Record, merge_record

Log = dict[str, Record]


def merge_logs(local: Log, remote: Log) -> Log:
    """Return the union of ``local`` and ``remote``, merging shared ids.

    Commutative and idempotent: ``merge_logs(a, b) == merge_logs(b, a)`` and
    ``merge_logs(x, x) == x``, so pull order between devices never matters
    and a repeated sync tick is a no-op.

    Args:
        local: This device's current full log (including tombstones).
        remote: Another device's last-pushed full log.

    Returns:
        The merged log, containing every id present in either input.
    """
    merged: Log = dict(local)
    for record_id, remote_record in remote.items():
        local_record = merged.get(record_id)
        merged[record_id] = (
            remote_record
            if local_record is None
            else merge_record(local_record, remote_record)
        )
    return merged
