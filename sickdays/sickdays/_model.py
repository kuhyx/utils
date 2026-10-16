# Copyright (c) 2026 Krzysztof Rudnicki
"""Translating between a sick day and a crdt-sync ``Record``.

The record id *is* the ISO date, so two devices marking the same day produce
the same record and converge instead of accumulating duplicates.

Adding and removing are a last-writer-wins flip of the ``state`` field, every
field stamped with one hybrid logical clock tick. Merging two copies keeps,
per field, the one with the greater clock -- so the most recent add or
remove of a date wins on every device, and a removed day can be added again
(and removed again) any number of times. A tombstone (``Record.deleted``)
would not allow that: crdt-sync OR-merges it, so a deleted date could never
come back. Nothing here ever sets it, and a tombstoned record reads as "not
sick".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from crdt_sync import Hlc, Record

from sickdays._constants import FIELD_ACTOR, FIELD_STATE, STATE_CLEARED, STATE_SICK
from sickdays._day import parse_iso, to_iso

if TYPE_CHECKING:
    from datetime import date

    from crdt_sync import Log


@dataclass(frozen=True)
class SickDay:
    """One day's entry, as the rest of the package wants to see it.

    Attributes:
        day: The calendar date.
        is_sick: Whether the day is currently a sick day.
        actor: Which device last changed it.
    """

    day: date
    is_sick: bool
    actor: str = ""


def _field_str(record: Record, name: str) -> str:
    field = record.fields.get(name)
    if field is None:
        return ""
    value = field[0]
    return value if isinstance(value, str) else ""


def is_sick_record(record: Record) -> bool:
    """Whether ``record`` currently marks its day sick.

    Anything not understood -- a tombstone, a missing or unknown state --
    reads as "not sick": the gates apply.
    """
    if record.deleted:
        return False
    return _field_str(record, FIELD_STATE) == STATE_SICK


def to_sick_day(record: Record) -> SickDay | None:
    """Build a :class:`SickDay` from ``record``, or None if its id is junk."""
    try:
        day = parse_iso(record.id)
    except ValueError:
        return None
    return SickDay(
        day=day,
        is_sick=is_sick_record(record),
        actor=_field_str(record, FIELD_ACTOR),
    )


def sick_dates(log: Log) -> frozenset[date]:
    """Every date ``log`` currently marks sick (junk ids skipped)."""
    days: set[date] = set()
    for record in log.values():
        entry = to_sick_day(record)
        if entry is not None and entry.is_sick:
            days.add(entry.day)
    return frozenset(days)


def latest_hlc(log: Log, node_id: str) -> Hlc | None:
    """Return the greatest clock this node has issued anywhere in ``log``.

    Feeding this back into :meth:`Hlc.new_tick` keeps the node's clock
    monotonic across process restarts, so a fresh process never issues a
    tick that loses to its own earlier write.
    """
    ticks = [
        hlc
        for record in log.values()
        for _, hlc in record.fields.values()
        if hlc.node_id == node_id
    ]
    return max(ticks) if ticks else None


def build_record(entry: SickDay, hlc: Hlc) -> Record:
    """Return the record expressing ``entry``, every field stamped ``hlc``.

    One tick for every field, so a concurrent add and remove of one day
    resolve together rather than interleaving state from one device and the
    actor from the other.
    """
    state = STATE_SICK if entry.is_sick else STATE_CLEARED
    return Record(
        id=to_iso(entry.day),
        fields={
            FIELD_STATE: (state, hlc),
            FIELD_ACTOR: (entry.actor, hlc),
        },
    )
