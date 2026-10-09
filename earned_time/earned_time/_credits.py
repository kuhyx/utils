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
from earned_time._match import CREDIT_STAMPS

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


def credit_units(earner: Earner, ledger: Path, key_file: Path, day: date) -> int | None:
    """How many verified credit rows count for ``day`` -- a counted earner's units.

    Args:
        earner: A ledger-backed earner (it must have ``match``).
        ledger: The gate's ledger file, resolved by the caller.
        key_file: The shared HMAC key, resolved by the caller.
        day: The local day the rows must count for (by ``match``).

    Returns:
        The count (``0`` included), or ``None`` when the ledger or key could
        not be read -- never "no units". A row repeated under the same
        ``entry_id`` (a replayed write) counts once. The earner's
        ``max_units`` is applied by :func:`~earned_time.resolve`, not here.

    Raises:
        ValueError: ``earner`` has no ``match``; its answer is the consumer's.
    """
    rows = counting_rows(earner, ledger, key_file, day_window(day))
    if rows is None:
        return None
    ids: set[object] = set()
    units = 0
    for row in rows:
        entry_id = row.get("entry_id")
        if entry_id is not None and entry_id in ids:
            continue
        ids.add(entry_id)
        units += 1
    return units
