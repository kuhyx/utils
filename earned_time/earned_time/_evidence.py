# Copyright (c) 2026 Krzysztof Rudnicki
"""What a gate has really paid out: the evidence :mod:`earned_time._maturity` judges.

A *real* credit is a signed ``credit`` row the earner's matcher accepts, that
no human granted by hand and that pays something -- a gate's own re-evaluation
grant (``detail.grant_of``) may pay 0. A manual grant is exactly the evidence
that the gate did *not* work, so no matcher may count it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Final, TypeGuard

from earned_time._credits import credit_time, day_window
from earned_time._ledger import read_key, read_rows, verified

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from earned_time._policy import Earner

# Rows a human granted by hand: the gate did not earn them.
MANUAL_SOURCES: Final = frozenset({"manual", "manual_grant"})
MANUAL_PREFIXES: Final = ("manual:", "manual_grant:")


def real_credit(row: object, key: bytes) -> TypeGuard[dict[str, object]]:
    """Whether a ledger row is signed, a credit, not manual, and pays something.

    A gate re-evaluation grant (``detail.grant_of``) counts at ``amount`` 0;
    the manual exclusions still apply to it.

    The matcher is asked separately (:func:`credit_day`): this is the part no
    matcher may loosen -- ``anki_match`` alone accepts a ``manual_grant`` row.
    """
    if not isinstance(row, dict) or row.get("kind") != "credit":
        return False
    if not verified(row, key) or _is_manual(row):
        return False
    return _pays(row)


def _is_manual(row: dict[str, object]) -> bool:
    """Whether a human granted ``row`` by hand (its source or its entry id)."""
    detail = row.get("detail")
    if isinstance(detail, dict) and detail.get("source") in MANUAL_SOURCES:
        return True
    return str(row.get("entry_id")).startswith(MANUAL_PREFIXES)


def _pays(row: dict[str, object]) -> bool:
    """``amount > 0`` (or no amount); ``amount`` 0 only for a gate's own grant."""
    if "amount" not in row:
        return True
    amount = row["amount"]
    if not isinstance(amount, int | float) or amount < 0:
        return False
    return bool(amount) or _is_grant(row.get("detail"))


def _is_grant(detail: object) -> bool:
    """Whether ``detail`` marks a gate re-evaluation grant (``grant_of``).

    book-guard re-grades a past session's bonus under the current rule and
    signs the result as its own ``bonus:`` row, paying ``amount`` 0 when no
    pages were added: the gate worked that day, so it still counts.
    """
    if not isinstance(detail, dict):
        return False
    grant_of = detail.get("grant_of")
    return isinstance(grant_of, str) and bool(grant_of)


def _candidate_days(earner: Earner, row: dict[str, object]) -> Iterator[date]:
    """Days a row might count for: its stamp's day, its ``day``, its Anki day."""
    stamp = credit_time(earner, row)
    if stamp is not None:
        yield datetime.fromtimestamp(stamp, tz=UTC).astimezone().date()
    detail = row.get("detail")
    anki_day = detail.get("anki_day") if isinstance(detail, dict) else None
    for raw in (row.get("day"), anki_day):
        try:
            yield date.fromisoformat(str(raw))
        except ValueError:
            continue


def credit_day(earner: Earner, row: dict[str, object]) -> date | None:
    """The local day ``earner.match`` counts ``row`` for, or ``None``.

    The matcher decides, exactly as it does for today's answer; the
    candidates only say which days to ask it about.

    Raises:
        ValueError: ``earner`` has no ``match``.
    """
    if earner.match is None:
        msg = f"earner {earner.name!r} has no shared reader; supply its answer"
        raise ValueError(msg)
    match = earner.match
    for day in dict.fromkeys(_candidate_days(earner, row)):
        if match(row, day_window(day)):
            return day
    return None


def credit_history(
    earner: Earner, ledger: Path, key_file: Path, today: date, reasons: list[str]
) -> tuple[list[date], int] | None:
    """Sorted real-credit days up to ``today``, and how many rows paid them.

    ``None`` -- with the reason appended to ``reasons`` -- when the key or
    the ledger cannot be read. A replayed ``entry_id`` counts once.
    """
    key = read_key(key_file)
    if key is None:
        reasons.append(f"could not check: HMAC key {key_file} unreadable")
        return None
    rows = read_rows(ledger, earner)
    if rows is None:
        reasons.append(f"could not check: ledger {ledger} unreadable")
        return None
    days: set[date] = set()
    ids: set[object] = set()
    paid = 0
    for row in rows:
        if not real_credit(row, key):
            continue
        day = credit_day(earner, row)
        entry_id = row.get("entry_id")
        if day is None or day > today or (entry_id is not None and entry_id in ids):
            continue
        ids.add(entry_id)
        days.add(day)
        paid += 1
    return sorted(days), paid
