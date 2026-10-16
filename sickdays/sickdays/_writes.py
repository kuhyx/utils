# Copyright (c) 2026 Krzysztof Rudnicki
"""The two ways a write reaches the pool: a whole record, or one field update.

A whole-record write (add, remove, import) stamps every field with one tick.
A keep edit must not: it re-stamps only ``keep`` and ``actor``, leaving
``state`` on its own clock (:func:`sickdays._keep.with_keep`).

Every tick is issued *after* both this node's last tick and every clock
already on the day's record, so a write always beats what it was looking at,
even when another device's wall clock runs ahead of this one's. Without that,
a keep edit made under clock skew could be born older than ``state`` -- and a
keep older than ``state`` reads as stale.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from crdt_sync import Hlc

from sickdays._day import to_iso
from sickdays._errors import PastDateError
from sickdays._keep import with_keep
from sickdays._model import build_record, latest_hlc, record_hlc
from sickdays._store import write_pool

if TYPE_CHECKING:
    from datetime import date

    from crdt_sync import Log, Record

    from sickdays._model import SickDay
    from sickdays._paths import Paths


def refuse_past(day: date, reference: date, verb: str) -> None:
    """Raise :class:`PastDateError` when ``day`` is before ``reference``."""
    if day < reference:
        msg = (
            f"{to_iso(day)} has already passed -- sick days can only be "
            f"{verb} for today or later"
        )
        raise PastDateError(msg)


def next_tick(log: Log, actor: str, existing: Record | None) -> Hlc:
    """This node's next clock, later than its own and ``existing``'s ticks."""
    seen = [t for t in (latest_hlc(log, actor), record_hlc(existing)) if t is not None]
    return Hlc.new_tick(actor, max(seen) if seen else None)


def write_entry(log: Log, entry: SickDay, resolved: Paths) -> None:
    """Replace the day's whole record with ``entry`` and persist the pool."""
    key = to_iso(entry.day)
    tick = next_tick(log, entry.actor, log.get(key))
    log[key] = build_record(entry, tick)
    write_pool(resolved.log, log)


def write_keep(
    log: Log,
    existing: Record,
    keep: frozenset[str],
    *,
    actor: str,
    resolved: Paths,
) -> None:
    """Re-stamp only ``keep`` and ``actor`` on ``existing`` and persist."""
    tick = next_tick(log, actor, existing)
    log[existing.id] = with_keep(existing, keep, actor=actor, tick=tick)
    write_pool(resolved.log, log)
