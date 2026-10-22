# Copyright (c) 2026 Krzysztof Rudnicki
"""Ask, add, remove, import -- the whole public surface.

:func:`is_sick_day` is the one every gate calls, and it is deliberately the
cheapest thing here: one local file read, no network, no lock. It never
raises: an unreadable pool is logged and reads as "not sick", so the failure
mode is "the gates apply", never "everything is switched off".

There is no cap, no budget and no justification. Every day is normal until
someone marks it sick, and only today or a later day can be marked or
un-marked -- never a past one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from crdt_sync import load_device_identity

from sickdays._audit import record_event
from sickdays._conflict import ensure_not_free, free_day_predicate
from sickdays._day import to_iso, today
from sickdays._errors import AlreadySickError, NotSickError
from sickdays._keep import normalise_keep
from sickdays._model import SickDay, is_sick_record, sick_dates
from sickdays._paths import Paths, resolve_paths
from sickdays._store import read_pool, read_pool_strict
from sickdays._writes import refuse_past, write_entry

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import date
    from pathlib import Path

    from crdt_sync import Log, Record

    from sickdays._conflict import FreePredicate


def load(log_path: Path | None = None) -> Log:
    """Read the pool. Missing reads as empty; unreadable is logged, then empty."""
    return read_pool(log_path if log_path is not None else resolve_paths(None).log)


def actor_id(paths: Paths | None = None) -> str:
    """This install's persisted device uuid, created on first call."""
    return load_device_identity(resolve_paths(paths).device_id).device_id


def require_sick(log: Log, day: date) -> Record:
    """The record that makes ``day`` sick in ``log``.

    Raises:
        NotSickError: ``day`` is not a sick day.
    """
    existing = log.get(to_iso(day))
    if existing is None or not is_sick_record(existing):
        msg = f"{to_iso(day)} is not a sick day"
        raise NotSickError(msg)
    return existing


def is_sick_day(
    day: date | None = None,
    *,
    log_path: Path | None = None,
    now: date | None = None,
) -> bool:
    """Whether ``day`` (default: today) is a sick day. Never raises."""
    target = day if day is not None else today(now)
    record = load(log_path).get(to_iso(target))
    return record is not None and is_sick_record(record)


def sick_days(*, log_path: Path | None = None) -> frozenset[date]:
    """Every date currently marked sick, past and future."""
    return sick_dates(load(log_path))


def add_sick_day(
    day: date,
    *,
    keep: Iterable[str] = (),
    is_free: FreePredicate | None = None,
    paths: Paths | None = None,
    now: date | None = None,
) -> SickDay:
    """Mark ``day`` sick, everywhere, for every gate.

    Args:
        day: The day. Today or later.
        keep: Lockers that stay active on the day (:data:`sickdays.LOCKERS`);
            every other locker stands down. Default: none -- all stand down.
        is_free: "Is this a free day?"; ``None`` asks freedays, imported
            lazily (:func:`sickdays._conflict.free_day_predicate`).
        paths: Where the pool, uuid and audit trail live.
        now: Reference date, for tests.

    Returns:
        The stored entry.

    Raises:
        ValueError: ``keep`` names an unknown locker.
        PastDateError: ``day`` has already passed.
        AlreadySickError: ``day`` is already a sick day.
        FreeDayConflictError: ``day`` is a free day.
        ConflictCheckUnavailableError: The free-day pool cannot be checked.
        UnreadablePoolError: The local pool exists but cannot be parsed.
    """
    kept = normalise_keep(keep)
    resolved = resolve_paths(paths)
    refuse_past(day, today(now), "added")
    log = read_pool_strict(resolved.log)
    existing = log.get(to_iso(day))
    if existing is not None and is_sick_record(existing):
        msg = f"{to_iso(day)} is already a sick day"
        raise AlreadySickError(msg)
    ensure_not_free(day, is_free if is_free is not None else free_day_predicate())
    entry = SickDay(day=day, is_sick=True, actor=actor_id(resolved), keep=kept)
    write_entry(log, entry, resolved)
    record_event("add", day, actor=entry.actor, keep=kept, paths=resolved)
    return entry


def remove_sick_day(
    day: date,
    *,
    paths: Paths | None = None,
    now: date | None = None,
) -> SickDay:
    """Make ``day`` a normal day again. Today or later only.

    Raises:
        PastDateError: ``day`` has already passed.
        NotSickError: ``day`` is not a sick day.
        UnreadablePoolError: The local pool exists but cannot be parsed.
    """
    resolved = resolve_paths(paths)
    refuse_past(day, today(now), "removed")
    log = read_pool_strict(resolved.log)
    require_sick(log, day)
    entry = SickDay(day=day, is_sick=False, actor=actor_id(resolved))
    write_entry(log, entry, resolved)
    record_event("remove", day, actor=entry.actor, paths=resolved)
    return entry


def import_legacy(days: Iterable[date], *, paths: Paths | None = None) -> list[date]:
    """Migration only: record ``days`` as sick, past dates included.

    The one writer that may write the past -- used once, for screen-locker's
    ``sick_history.json`` (2026-06-21, 2026-07-24), both of which predate
    every gate start. No free-day check: those dates predate freedays.
    Idempotent: a day already sick is skipped and gets no audit line.

    Returns:
        The days actually written, ascending.

    Raises:
        UnreadablePoolError: The local pool exists but cannot be parsed.
    """
    resolved = resolve_paths(paths)
    log = read_pool_strict(resolved.log)
    node = actor_id(resolved)
    written: list[date] = []
    for day in sorted(set(days)):
        existing = log.get(to_iso(day))
        if existing is not None and is_sick_record(existing):
            continue
        write_entry(log, SickDay(day=day, is_sick=True, actor=node), resolved)
        record_event("import", day, actor=node, paths=resolved)
        written.append(day)
    return written
