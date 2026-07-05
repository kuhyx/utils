"""Record: a per-field LWW map with a sticky (monotonic) delete flag.

This is the unit CRDT merges operate on. It's deliberately domain-agnostic --
translating an app's own model (a note, a food-log entry, a workout entry,
a wake-time value) to and from ``Record`` is each app's job, not this
library's.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crdt_sync._hlc import Hlc

Field = tuple[Any, Hlc]


@dataclass(frozen=True)
class Record:
    """One CRDT record: an id, per-field LWW values, and a sticky tombstone.

    Attributes:
        id: Stable identifier, unique within one ``Log``.
        fields: Field name -> ``(value, Hlc)``. Concurrent edits to the same
            field converge to whichever side has the greater ``Hlc``.
        deleted: Whether this record is tombstoned. Deletion is monotonic:
            once true on either side of a merge, it stays true.
        deleted_hlc: The clock value of the delete, if any -- kept for
            informational/ordering purposes only; it does not participate in
            the merge decision (that's a plain boolean OR, see
            :func:`merge_record`).
    """

    id: str
    fields: dict[str, Field]
    deleted: bool = False
    deleted_hlc: Hlc | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "id": self.id,
            "fields": {
                name: [value, hlc.to_str()]
                for name, (value, hlc) in self.fields.items()
            },
            "deleted": self.deleted,
            "deleted_hlc": self.deleted_hlc.to_str()
            if self.deleted_hlc is not None
            else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Record:
        """Parse the format produced by :meth:`to_dict`."""
        fields = {
            name: (value, Hlc.from_str(hlc_str))
            for name, (value, hlc_str) in data["fields"].items()
        }
        deleted_hlc_str = data.get("deleted_hlc")
        deleted_hlc = (
            Hlc.from_str(deleted_hlc_str) if deleted_hlc_str is not None else None
        )
        return cls(
            id=data["id"],
            fields=fields,
            deleted=bool(data["deleted"]),
            deleted_hlc=deleted_hlc,
        )


def merge_field(a: Field, b: Field) -> Field:
    """Return whichever of ``a``, ``b`` has the greater ``Hlc``.

    Ties (equal ``Hlc``) keep ``a``; two ticks never compare equal across
    different nodes (see :class:`crdt_sync._hlc.Hlc`), so a tie only happens
    when both sides are literally the same tick re-merged, in which case the
    value is expected to be identical anyway.
    """
    return a if a[1] >= b[1] else b


def _merge_deleted_hlc(a: Record, b: Record) -> Hlc | None:
    """Return the delete-clock to keep, informational only (see class docs)."""
    if a.deleted and b.deleted:
        if a.deleted_hlc is None:
            return b.deleted_hlc
        if b.deleted_hlc is None:
            return a.deleted_hlc
        return max(a.deleted_hlc, b.deleted_hlc)
    if a.deleted:
        return a.deleted_hlc
    if b.deleted:
        return b.deleted_hlc
    return None


def merge_record(a: Record, b: Record) -> Record:
    """Merge two versions of the same record.

    Per-field last-writer-wins over the union of field names, plus a sticky
    delete: ``deleted = a.deleted or b.deleted``, never the other way around.
    A tombstone can never be resurrected by merging in an older, non-deleted
    copy pulled from a device that hasn't seen the delete yet.

    Commutative and idempotent: ``merge_record(a, b) == merge_record(b, a)``
    and ``merge_record(a, a) == a``.

    Raises:
        ValueError: If ``a.id != b.id`` -- merging two different records is
            a caller bug, not a case to silently paper over.
    """
    if a.id != b.id:
        msg = f"cannot merge records with different ids: {a.id!r} != {b.id!r}"
        raise ValueError(msg)
    merged_fields = dict(a.fields)
    for name, b_field in b.fields.items():
        a_field = merged_fields.get(name)
        merged_fields[name] = (
            b_field if a_field is None else merge_field(a_field, b_field)
        )
    return Record(
        id=a.id,
        fields=merged_fields,
        deleted=a.deleted or b.deleted,
        deleted_hlc=_merge_deleted_hlc(a, b),
    )
