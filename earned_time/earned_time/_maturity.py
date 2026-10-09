# Copyright (c) 2026 Krzysztof Rudnicki
"""How far to trust a gate: computed from its signed ledger, never listed.

A gate is **new** until it has paid out for real and kuhy has confirmed a
working session (``Earner.confirmed_on``), **mature** once it has paid on
:data:`MATURE_MIN_CREDIT_DAYS` distinct days and its first payout is at least
:data:`MATURE_MIN_AGE_DAYS` old, and **maturing** in between. A new gate is
lenient (no penalty before it has worked); a mature one is suspicious of
"just grant me the points".

Only a *real* credit counts (:func:`~earned_time._evidence.real_credit`):
HMAC-verified, accepted by the earner's matcher, not a hand-granted row, and
paying something. A manual grant is exactly the evidence that the gate did
*not* work.

**The penalty never starts before the gate has paid out**
(:func:`penalty_start`): a gate that never earned anything cannot cost
anything. The adjustment can only delay a penalty. A ledger or key that
cannot be read is "could not check": no evidence of maturity.

**Fail closed once confirmed.** A gate with a hand-set ``confirmed_on`` has
been seen to work, so "no credit on record" -- unreadable key or ledger, a
deleted ledger, an emptied one -- cannot lift its penalty: it falls back to
:func:`confirmed_start`. Only a gate without ``confirmed_on`` is lenient.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Final, Literal

from earned_time._evidence import credit_history

if TYPE_CHECKING:
    from pathlib import Path

    from earned_time._policy import Earner

Level = Literal["new", "maturing", "mature"]

# Distinct days with a real credit, and how old the first one must be.
MATURE_MIN_CREDIT_DAYS: Final = 14
MATURE_MIN_AGE_DAYS: Final = 21

_DAY: Final = timedelta(days=1)


@dataclass(frozen=True)
class Maturity:
    """One gate's verdict, with the evidence behind it.

    Attributes:
        name: The earner's registry name.
        level: ``"new"``, ``"maturing"`` or ``"mature"``.
        reasons: Human-readable, in the order they were decided.
        credit_days: Distinct local days, up to the verdict's day, with a
            real credit.
        credit_rows: Real credit rows behind them (a replayed ``entry_id`` once).
        first_credit: The first such day, or ``None``.
        last_credit: The last such day, or ``None``.
        confirmed_on: The earner's ``confirmed_on``.
        penalty_from: The earner's ``penalty_from``.
        penalty_start: The effective first penalised day
            (:func:`penalty_start`); ``None`` means not penalised.
        checked: ``False`` when the ledger or the key could not be read.
    """

    name: str
    level: Level
    reasons: tuple[str, ...]
    credit_days: int
    credit_rows: int
    first_credit: date | None
    last_credit: date | None
    confirmed_on: date | None
    penalty_from: date | None
    penalty_start: date | None
    checked: bool


def confirmed_start(earner: Earner) -> date | None:
    """``max(penalty_from, day after confirmed_on)``; ``None`` for a pure bonus.

    What is left of :func:`penalty_start` when the ledger was not consulted:
    a ``confirmed_on`` of ``None`` drops out of the max.
    """
    if earner.penalty_from is None:
        return None
    if earner.confirmed_on is None:
        return earner.penalty_from
    return max(earner.penalty_from, earner.confirmed_on + _DAY)


def penalty_start(earner: Earner, first_credit: date | None) -> date | None:
    """The first day ``earner``'s penalty may apply, given its first real credit.

    ``max(penalty_from, day after first_credit, day after confirmed_on)``;
    a ``confirmed_on`` of ``None`` drops out of the max. No first credit
    (never paid out, or could not check): :func:`confirmed_start` when kuhy
    set ``confirmed_on`` -- fail closed, deleting a ledger lifts nothing --
    else ``None``, not penalised. ``None`` for a pure bonus. Never earlier
    than ``penalty_from``.
    """
    start = confirmed_start(earner)
    if start is None:
        return None
    if first_credit is None:
        return start if earner.confirmed_on is not None else None
    return max(start, first_credit + _DAY)


def _level(days: list[date], earner: Earner, today: date, reasons: list[str]) -> Level:
    if not days:
        reasons.append("no verified credit yet")
        return "new"
    if earner.confirmed_on is None:
        reasons.append("no confirmed_on: kuhy has not confirmed a real session")
        return "new"
    age = (today - days[0]).days
    if len(days) >= MATURE_MIN_CREDIT_DAYS and age >= MATURE_MIN_AGE_DAYS:
        reasons.append(
            f"{len(days)} credit days >= {MATURE_MIN_CREDIT_DAYS} and first "
            f"credit {age} days ago >= {MATURE_MIN_AGE_DAYS}"
        )
        return "mature"
    reasons.append(
        f"{len(days)}/{MATURE_MIN_CREDIT_DAYS} credit days, first credit "
        f"{age}/{MATURE_MIN_AGE_DAYS} days ago"
    )
    return "maturing"


def _penalty_reason(
    earner: Earner, start: date | None, first: date | None, *, checked: bool
) -> str:
    if earner.penalty_from is None:
        return "no penalty_from: a pure bonus"
    if start is not None and first is None:
        why = "could not check" if not checked else "no verified credit"
        return (
            f"{why} but confirmed_on {earner.confirmed_on}: "
            f"fail closed, penalty from {start}"
        )
    if start is None:
        return f"never paid out: no penalty (penalty_from {earner.penalty_from})"
    if start > earner.penalty_from:
        return f"penalty delayed from {earner.penalty_from} to {start}"
    return f"penalty from {start}, as registered"


def maturity(
    earner: Earner, ledger: Path, key_file: Path, today: date | None = None
) -> Maturity:
    """Classify ``earner`` from its signed ledger, as of ``today`` (default now).

    Args:
        earner: A ledger-backed earner (it must have ``match``).
        ledger: The gate's ledger file, resolved by the caller.
        key_file: The shared HMAC key, resolved by the caller.
        today: The verdict's day; credits after it are ignored.

    Returns:
        The verdict. An unreadable ledger or key is ``checked=False``: level
        ``"new"``, with the reason recorded; no penalty unless ``confirmed_on``
        is set (then :func:`confirmed_start`, fail closed).

    Raises:
        ValueError: ``earner`` has no ``match``; its answer is the consumer's.
    """
    if earner.match is None:
        msg = f"earner {earner.name!r} has no shared reader; supply its answer"
        raise ValueError(msg)
    target = today or datetime.now(tz=UTC).astimezone().date()
    reasons: list[str] = []
    found = credit_history(earner, ledger, key_file, target, reasons)
    days, paid = found if found is not None else ([], 0)
    level = _level(days, earner, target, reasons)
    first = days[0] if days else None
    start = penalty_start(earner, first)
    reasons.append(_penalty_reason(earner, start, first, checked=found is not None))
    return Maturity(
        name=earner.name,
        level=level,
        reasons=tuple(reasons),
        credit_days=len(days),
        credit_rows=paid,
        first_credit=first,
        last_credit=days[-1] if days else None,
        confirmed_on=earner.confirmed_on,
        penalty_from=earner.penalty_from,
        penalty_start=start,
        checked=found is not None,
    )
