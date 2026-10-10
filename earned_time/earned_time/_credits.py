# Copyright (c) 2026 Krzysztof Rudnicki
"""Day-scoped questions about a gate's signed ledger: when, and how many.

:func:`~earned_time._ledger.done_today` asks "is there a credit yet today?".
These ask about a whole local day: when the first counting credit happened
(:func:`first_credit_at`) and how many count (:func:`credit_units`, a counted
earner's units). The same rules hold: paths are passed in, and ``None`` is
"could not check", never "no".
"""

from __future__ import annotations

from datetime import date, datetime, time
import logging
from typing import TYPE_CHECKING, Final

from earned_time._ledger import counting_rows
from earned_time._match import CREDIT_STAMPS, ROW_UNITS

if TYPE_CHECKING:
    from pathlib import Path

    from earned_time._policy import Earner, Window

_logger: Final = logging.getLogger(__name__)


def day_window(day: date) -> Window:
    """``day``'s local midnight to its last microsecond, as unix seconds.

    Each end is localised on its own, so a DST day gets its real length.
    """
    start = datetime.combine(day, time.min).astimezone()
    end = datetime.combine(day, time.max).astimezone()
    return start.timestamp(), end.timestamp()


def credit_time(earner: Earner, row: dict[str, object]) -> float | None:
    """When a credit row's work happened, as unix seconds; ``None`` if unusable.

    The detail field its matcher decides on (``CREDIT_STAMPS``) (LeetCode's
    ``submitted_at``, reading's ``ended_at`` -- the stamp ``match`` decides
    on), else the row's ``created_at``.
    """
    detail = row.get("detail")
    stamp = CREDIT_STAMPS.get(earner.match) if earner.match is not None else None
    if stamp is not None and isinstance(detail, dict):
        try:
            return float(str(detail.get(stamp)))
        except ValueError:
            pass
    raw = row.get("created_at")
    try:
        return datetime.fromisoformat(str(raw)).timestamp()
    except ValueError:
        _logger.warning(
            "%s credit %r has no usable time", earner.label, row.get("entry_id")
        )
        return None


def first_credit_at(
    earner: Earner, ledger: Path, key_file: Path, day: date
) -> float | None:
    """When ``earner``'s first verified credit that counts for ``day`` happened.

    Args:
        earner: A ledger-backed earner (it must have ``match``).
        ledger: The gate's ledger file, resolved by the caller.
        key_file: The shared HMAC key, resolved by the caller.
        day: The local day the credit must count for (by ``match``).

    Returns:
        The earliest :func:`credit_time` among the counting rows, as unix
        seconds. ``None`` when no row counts, or when the ledger or key could
        not be read -- never a time that was not checked.

    Raises:
        ValueError: ``earner`` has no ``match``; its answer is the consumer's.
    """
    rows = counting_rows(earner, ledger, key_file, day_window(day))
    if rows is None:
        return None
    times = [t for t in (credit_time(earner, row) for row in rows) if t is not None]
    return min(times, default=None)


def row_units(earner: Earner, row: dict[str, object]) -> int:
    """Units one counting row pays: its own count (``ROW_UNITS``), else 1.

    Only the tutor's rows carry a count (``detail.minutes``, 0.8.0); a row
    whose count is unusable pays 0 (``tutor_match`` already refuses it).
    """
    reader = ROW_UNITS.get(earner.match) if earner.match is not None else None
    return 1 if reader is None else reader(row) or 0


def credit_units(earner: Earner, ledger: Path, key_file: Path, day: date) -> int | None:
    """How many units the verified credit rows pay for ``day``.

    Each row pays :func:`row_units`: 1 for most earners (the workout), its
    ``detail.minutes`` for the tutor (a 0.7.0 block row without it, 15), so a
    day mixing block rows and minute rows sums both.

    Args:
        earner: A ledger-backed earner (it must have ``match``).
        ledger: The gate's ledger file, resolved by the caller.
        key_file: The shared HMAC key, resolved by the caller.
        day: The local day the rows must count for (by ``match``).

    Returns:
        The sum (``0`` included), or ``None`` when the ledger or key could
        not be read -- never "no units". An ``entry_id`` pays once: rows
        repeated under one id (a replayed write) pay the smallest of their
        counts, so a rewrite can never raise a credit. The earner's
        ``max_units`` is applied by :func:`~earned_time.resolve`, not here.

    Raises:
        ValueError: ``earner`` has no ``match``; its answer is the consumer's.
    """
    rows = counting_rows(earner, ledger, key_file, day_window(day))
    if rows is None:
        return None
    by_id: dict[object, int] = {}
    anonymous = 0
    for row in rows:
        units = row_units(earner, row)
        entry_id = row.get("entry_id")
        if entry_id is None:
            anonymous += units
        else:
            by_id[entry_id] = min(units, by_id.get(entry_id, units))
    return anonymous + sum(by_id.values())
