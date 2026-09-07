"""Translating between a free day and a crdt-sync ``Record``.

The record id *is* the ISO date, so two devices marking the same day produce
the same record and converge instead of accumulating duplicates. Marking and
un-marking are a last-writer-wins flip of one field rather than a create and
a delete, because crdt-sync tombstones are monotonic -- deleting the record
would burn that date permanently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from crdt_sync import Hlc, Record

from freedays._constants import (
    FIELD_ACTOR,
    FIELD_CONSUMED,
    FIELD_REASON,
    FIELD_STATE,
    STATE_CLEARED,
    STATE_FREE,
)
from freedays._day import parse_iso, to_iso

if TYPE_CHECKING:
    from datetime import date

    from crdt_sync import Log


@dataclass(frozen=True)
class FreeDay:
    """One day's entry, as the rest of the package wants to see it.

    Attributes:
        day: The calendar date.
        is_free: Whether the day currently stands the gates down.
        consumed: Whether the day arrived while free, and so stays spent even
            after being released.
        actor: Which device last changed it.
        reason: Optional free text. Never required -- a free day carries no
            justification burden by design.
    """

    day: date
    is_free: bool
    consumed: bool = False
    actor: str = ""
    reason: str = ""


def _field_str(record: Record, name: str) -> str:
    field = record.fields.get(name)
    if field is None:
        return ""
    value = field[0]
    return value if isinstance(value, str) else ""


def is_consumed_record(record: Record) -> bool:
    """Whether ``record``'s day is spent regardless of its current state."""
    field = record.fields.get(FIELD_CONSUMED)
    return bool(field[0]) if field is not None else False


def is_free_record(record: Record) -> bool:
    """Whether ``record`` currently marks its day free.

    A tombstoned record counts as not free: nothing in this package creates
    one, but a hand-edited or future-format log might, and "not free" is the
    safe reading of a record we do not understand.
    """
    if record.deleted:
        return False
    return _field_str(record, FIELD_STATE) == STATE_FREE


def to_free_day(record: Record) -> FreeDay | None:
    """Build a :class:`FreeDay` from ``record``, or None if its id is junk."""
    try:
        day = parse_iso(record.id)
    except ValueError:
        return None
    return FreeDay(
        day=day,
        is_free=is_free_record(record),
        consumed=is_consumed_record(record),
        actor=_field_str(record, FIELD_ACTOR),
        reason=_field_str(record, FIELD_REASON),
    )


def latest_hlc(log: Log, node_id: str) -> Hlc | None:
    """Return the greatest clock this node has issued anywhere in ``log``.

    Feeding this back into :meth:`Hlc.new_tick` keeps the node's clock
    monotonic across process restarts, which is what stops a fresh process
    from issuing a tick that loses to its own earlier write.
    """
    ticks = [
        hlc
        for record in log.values()
        for _, hlc in record.fields.values()
        if hlc.node_id == node_id
    ]
    return max(ticks) if ticks else None


def build_record(entry: FreeDay, hlc: Hlc) -> Record:
    """Return the record expressing ``entry``, stamped with ``hlc``.

    Every field carries the same tick, so a concurrent mark and un-mark of
    one day resolve together rather than interleaving into a state from one
    device and a reason from the other.

    ``entry.consumed`` is only ever ``True`` when the caller has already
    established the day has arrived; no caller writes it back to ``False``
    over a ``True``, which is what keeps it sticky across merges.
    """
    state = STATE_FREE if entry.is_free else STATE_CLEARED
    return Record(
        id=to_iso(entry.day),
        fields={
            FIELD_STATE: (state, hlc),
            FIELD_CONSUMED: (entry.consumed, hlc),
            FIELD_ACTOR: (entry.actor, hlc),
            FIELD_REASON: (entry.reason, hlc),
        },
    )
