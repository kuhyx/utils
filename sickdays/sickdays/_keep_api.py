# Copyright (c) 2026 Krzysztof Rudnicki
"""Per-locker questions and the keep edit (0.2.0).

A sick day may keep some lockers active. A locker *stands down* on a day iff
the day is sick **and** the locker is not in that day's keep set.
:func:`stands_down` is what a gate asks; like :func:`sickdays.is_sick_day` it
reads one local file and never raises for a data problem. An unreadable pool
reads as "not sick" and a malformed keep set as "every locker kept" -- both
mean the locks apply.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sickdays._api import actor_id, load, require_sick
from sickdays._audit import record_event
from sickdays._day import to_iso, today
from sickdays._keep import normalise_keep, read_keep, validate_locker
from sickdays._model import SickDay, is_sick_record
from sickdays._paths import resolve_paths
from sickdays._store import read_pool_strict
from sickdays._writes import refuse_past, write_keep

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import date
    from pathlib import Path

    from sickdays._paths import Paths


def kept_lockers(
    day: date | None = None,
    *,
    log_path: Path | None = None,
    now: date | None = None,
) -> frozenset[str]:
    """The lockers ``day`` (default: today) keeps active; empty when not sick.

    Never raises: a malformed keep set is logged and reads as every locker.
    """
    target = day if day is not None else today(now)
    record = load(log_path).get(to_iso(target))
    if record is None or not is_sick_record(record):
        return frozenset()
    return read_keep(record)


def stands_down(
    locker: str,
    day: date | None = None,
    *,
    log_path: Path | None = None,
    now: date | None = None,
) -> bool:
    """Whether ``locker`` is switched off on ``day`` (default: today).

    True iff the day is sick and ``locker`` is not in its keep set. Never
    raises for a data problem -- every one of them answers ``False``.

    Raises:
        ValueError: ``locker`` is not one of :data:`sickdays.LOCKERS` (a
            programmer error, not a data problem).
    """
    validate_locker(locker)
    target = day if day is not None else today(now)
    record = load(log_path).get(to_iso(target))
    if record is None or not is_sick_record(record):
        return False
    return locker not in read_keep(record)


def set_kept_lockers(
    day: date,
    keep: Iterable[str],
    *,
    paths: Paths | None = None,
    now: date | None = None,
) -> SickDay:
    """Replace the kept lockers of an existing sick day. Today or later only.

    Only ``keep`` and ``actor`` are re-stamped; ``state`` keeps its clock,
    so this edit can never re-assert "sick" over a concurrent clear. An empty
    ``keep`` stands every locker down again.

    Returns:
        The stored entry.

    Raises:
        ValueError: ``keep`` names an unknown locker.
        PastDateError: ``day`` has already passed.
        NotSickError: ``day`` is not a sick day.
        UnreadablePoolError: The local pool exists but cannot be parsed.
    """
    kept = normalise_keep(keep)
    resolved = resolve_paths(paths)
    refuse_past(day, today(now), "changed")
    log = read_pool_strict(resolved.log)
    existing = require_sick(log, day)
    actor = actor_id(resolved)
    write_keep(log, existing, kept, actor=actor, resolved=resolved)
    record_event("keep", day, actor=actor, keep=kept, paths=resolved)
    return SickDay(day=day, is_sick=True, actor=actor, keep=kept)
