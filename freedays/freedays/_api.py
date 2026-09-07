"""Ask, mark, release, report -- the whole public surface.

:func:`is_free_day` is the one every gate app calls, and it is deliberately
the cheapest thing here: a single local file read, no network, no lock, no
clock beyond today's date. A gate fires from a systemd timer, and a sync
that hangs must never be able to hold one open or hold one shut.

Nothing in this module prompts, warns, or notifies. The pool is consulted
silently and reported only when someone asks for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from crdt_sync import Hlc, load_device_identity, read_log, write_log

from freedays._audit import record_event
from freedays._budget import (
    free_days_in_year,
    is_exhausted,
    remaining,
    spent_days_in_year,
)
from freedays._constants import DEFAULT_ANNUAL_BUDGET
from freedays._day import to_iso, today
from freedays._errors import (
    AlreadyFreeError,
    BudgetExhaustedError,
    NotFreeError,
    PastDateError,
)
from freedays._model import (
    FreeDay,
    build_record,
    is_consumed_record,
    is_free_record,
    latest_hlc,
    to_free_day,
)
from freedays._paths import Paths, resolve_paths

if TYPE_CHECKING:
    from datetime import date
    from pathlib import Path

    from crdt_sync import Log, Record


def load(log_path: Path | None = None) -> Log:
    """Read the pool from disk. A missing or corrupt file reads as empty.

    Takes a bare path rather than a :class:`Paths`: this and
    :func:`is_free_day` are what every gate app calls, and asking a gate to
    assemble a path bundle to answer one question is the wrong trade.
    """
    return read_log(log_path if log_path is not None else resolve_paths(None).log)


def save(log: Log, log_path: Path | None = None) -> None:
    """Write the pool to disk atomically."""
    write_log(log_path if log_path is not None else resolve_paths(None).log, log)


def actor_id(paths: Paths | None = None) -> str:
    """This install's persisted device uuid, created on first call."""
    return load_device_identity(resolve_paths(paths).device_id).device_id


def lookup(
    day: date | None = None,
    *,
    log_path: Path | None = None,
    now: date | None = None,
) -> FreeDay | None:
    """Return the entry for ``day``, or None if that day was never touched."""
    target = day if day is not None else today(now)
    record = load(log_path).get(to_iso(target))
    return to_free_day(record) if record is not None else None


def is_free_day(
    day: date | None = None,
    *,
    log_path: Path | None = None,
    now: date | None = None,
) -> bool:
    """Whether the gates stand down on ``day`` (default: today).

    This is the integration point every app calls. It reads one local file
    and nothing else, so it cannot block, and it answers False for anything
    it does not understand -- an unreadable pool means the normal rules
    apply, never that everything is switched off.
    """
    target = day if day is not None else today(now)
    record = load(log_path).get(to_iso(target))
    return record is not None and is_free_record(record)


def _next_hlc(log: Log, node_id: str) -> Hlc:
    return Hlc.new_tick(node_id, latest_hlc(log, node_id))


def _stays_consumed(existing: Record | None, day: date, reference: date) -> bool:
    """Whether the day is spent: it has arrived, or was already marked spent.

    OR-ing against the existing value is what keeps the flag sticky. Two
    devices either side of midnight can disagree about whether a day has
    arrived, and without this the one that thinks it is still tomorrow would
    write ``False`` over the other's ``True`` and hand back a day that was
    already used.
    """
    already = existing is not None and is_consumed_record(existing)
    return already or day <= reference


def mark(
    day: date,
    *,
    reason: str = "",
    paths: Paths | None = None,
    now: date | None = None,
    budget: int = DEFAULT_ANNUAL_BUDGET,
) -> FreeDay:
    """Mark ``day`` free, everywhere, for every app.

    Args:
        day: The day to take. Today or later.
        reason: Optional free text. Never required.
        paths: Where the pool, uuid and audit trail live.
        now: Reference date, for tests.
        budget: Days granted in ``day``'s calendar year.

    Returns:
        The stored entry.

    Raises:
        PastDateError: If ``day`` has already passed.
        AlreadyFreeError: If ``day`` is already free.
        BudgetExhaustedError: If that year has no days left.
    """
    resolved = resolve_paths(paths)
    reference = today(now)
    if day < reference:
        msg = (
            f"{to_iso(day)} has already passed -- free days are declared, not backdated"
        )
        raise PastDateError(msg)
    log = load(resolved.log)
    existing = log.get(to_iso(day))
    if existing is not None and is_free_record(existing):
        msg = f"{to_iso(day)} is already a free day"
        raise AlreadyFreeError(msg)
    if is_exhausted(log, day.year, budget=budget):
        msg = f"no free days left in {day.year} -- all {budget} are spent"
        raise BudgetExhaustedError(msg)

    node = actor_id(resolved)
    entry = FreeDay(
        day=day,
        is_free=True,
        consumed=_stays_consumed(existing, day, reference),
        actor=node,
        reason=reason,
    )
    log[to_iso(day)] = build_record(entry, _next_hlc(log, node))
    save(log, resolved.log)
    record_event("mark", day, actor=node, reason=reason, paths=resolved)
    return entry


def release(
    day: date,
    *,
    paths: Paths | None = None,
    now: date | None = None,
) -> FreeDay:
    """Give ``day`` back, and refund it only if it has not arrived yet.

    Releasing a future day returns it to the pool. Releasing today or a past
    day restores the gates from here on but does not refund it: those hours
    were already unguarded, and pretending otherwise would make the count
    mean nothing.

    Raises:
        NotFreeError: If ``day`` is not currently a free day.
    """
    resolved = resolve_paths(paths)
    reference = today(now)
    log = load(resolved.log)
    existing = log.get(to_iso(day))
    if existing is None or not is_free_record(existing):
        msg = f"{to_iso(day)} is not a free day"
        raise NotFreeError(msg)

    node = actor_id(resolved)
    entry = FreeDay(
        day=day,
        is_free=False,
        consumed=_stays_consumed(existing, day, reference),
        actor=node,
    )
    log[to_iso(day)] = build_record(entry, _next_hlc(log, node))
    save(log, resolved.log)
    record_event("release", day, actor=node, paths=resolved)
    return entry


@dataclass(frozen=True)
class Status:
    """A year's worth of pool state, for someone who went looking for it."""

    year: int
    budget: int
    spent: int
    left: int
    today_is_free: bool
    upcoming: list[date] = field(default_factory=list)
    taken: list[date] = field(default_factory=list)


def status(
    *,
    year: int | None = None,
    log_path: Path | None = None,
    now: date | None = None,
    budget: int = DEFAULT_ANNUAL_BUDGET,
) -> Status:
    """Summarise ``year`` (default: the current one). Never called on its own."""
    reference = today(now)
    target_year = year if year is not None else reference.year
    log = load(log_path)
    taken = spent_days_in_year(log, target_year)
    return Status(
        year=target_year,
        budget=budget,
        spent=len(taken),
        left=remaining(log, target_year, budget=budget),
        today_is_free=is_free_day(reference, log_path=log_path),
        upcoming=[d for d in free_days_in_year(log, target_year) if d > reference],
        taken=taken,
    )
