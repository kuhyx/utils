# Copyright (c) 2026 Krzysztof Rudnicki
"""Today's gaming budget and shutdown time: the base plus every earned term.

Both consumers call :func:`resolve` with their own answers and apply the
result: steam-backlog-enforcer the gaming minutes, screen-locker the shutdown
minutes. The sum is computed in exactly one place, so the two can no longer
disagree about what a day earned.

An answer is a unit count (``True``/``False`` work as 1/0) or ``None`` for
"could not check". ``None`` -- and an earner the consumer did not answer for at
all -- earns nothing: fail closed. The difference shows up only in
:attr:`Term.answer`, so the consumer can log or report it.

**Maturity can only delay a penalty.** Given ``first_credits`` (each earner's
first real credit, from :func:`earned_time.maturity`), a penalty starts no
earlier than the day after the gate first paid out
(:func:`~earned_time._maturity.penalty_start`). Without it a penalty starts at
``penalty_from``, as in 0.5.0. The same start spares the ladder floor: a gate
whose penalty has not started does not lower it (0.6.1).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
import logging
from typing import TYPE_CHECKING, Final

from earned_time._ladder import on_ladder, shutdown_ceiling_for
from earned_time._leisure import (
    gaming_base_minutes_for,
    gaming_ceiling_minutes_for,
    leisure_day,
)
from earned_time._maturity import confirmed_start, penalty_start
from earned_time._policy import SHUTDOWN_BASE_MINUTES, Earner
from earned_time._registry import all_earners, earners_for
from earned_time._resolution import Base, Resolution, Term
from earned_time._sick import sick_shutdown_from

if TYPE_CHECKING:
    from collections.abc import Mapping

_logger: Final = logging.getLogger(__name__)

Answer = int | bool | None


def _today() -> date:
    return datetime.now(tz=UTC).astimezone().date()


def _penalised(
    item: Earner, day: date, first_credits: Mapping[str, date | None] | None
) -> bool:
    """Whether ``item``'s cut is in force on ``day``.

    Without ``first_credits``: ``penalty_from`` alone, as in 0.5.0. With it:
    :func:`penalty_start` of the earner's first real credit (``None`` -- never
    paid out, or could not check -- is not penalised unless ``confirmed_on``
    is set: fail closed); an earner missing from it still waits for the day
    after its ``confirmed_on``.
    """
    if first_credits is None:
        return item.penalised_on(day)
    start = (
        penalty_start(item, first_credits[item.name])
        if item.name in first_credits
        else confirmed_start(item)
    )
    return start is not None and day >= start


def _shutdown_floor(day: date, earners: tuple[Earner, ...], cut: list[Earner]) -> int:
    """Shutdown of a day that earned nothing; ``cut``: the penalties in force.

    On the ladder: the ceiling minus the most each earner can pay (all of a
    capped earner's units), so doing everything lands exactly on the ceiling
    -- but only a pure bonus (no ``penalty_from``) or an earner in ``cut``: a
    gate whose penalty has not started cannot lower the floor (0.6.1). Before
    it: the old base minus the penalties in force.
    """
    if on_ladder(day):
        rungs = (e for e in earners if e.penalty_from is None or e in cut)
        return shutdown_ceiling_for(day) - sum(
            e.shutdown_for(e.max_units or 1, day) for e in rungs
        )
    return SHUTDOWN_BASE_MINUTES - sum(e.shutdown_minutes for e in cut)


def base_for(
    day: date | None = None,
    earners: tuple[Earner, ...] | None = None,
    *,
    first_credits: Mapping[str, date | None] | None = None,
    leisure: bool = False,
) -> Base:
    """The floor for ``day`` (default today) under ``earners`` (default its own).

    Gaming: every penalty in force, the most each earner can pay, taken off
    the gaming base. Shutdown: see :func:`_shutdown_floor` -- the two are
    derived separately so the ladder can never move a gaming minute.
    ``first_credits`` (per earner name) delays each penalty, and the ladder
    rung, to :func:`penalty_start`; omitted, 0.5.0's ``penalty_from`` applies.
    The gaming base is :func:`gaming_base_minutes_for` the day, or with
    ``leisure`` the leisure base whatever the date (:func:`leisure_day`).
    """
    target = day or _today()
    registry = earners_for(target) if earners is None else earners
    penalised = [e for e in registry if _penalised(e, target, first_credits)]
    return Base(
        gaming_minutes=gaming_base_minutes_for(leisure_day(target, leisure=leisure))
        - sum(e.max_gaming_minutes for e in penalised),
        shutdown_minutes=_shutdown_floor(target, registry, penalised),
    )


def _units(answer: Answer) -> int | None:
    if answer is None:
        return None
    return max(0, int(answer))


def _check_registered(
    answers: Mapping[str, Answer], registry: tuple[Earner, ...]
) -> None:
    """Raise ``KeyError`` for an answer no registry knows: a typo, not a "no"."""
    known = {e.name for e in (*registry, *all_earners())}
    unknown = sorted(set(answers) - known)
    if unknown:
        msg = f"not registered earners: {', '.join(unknown)}"
        raise KeyError(msg)


def _term(item: Earner, answers: Mapping[str, Answer], day: date) -> Term:
    """``item``'s term on ``day``; no answer at all is logged and earns nothing."""
    if item.name not in answers:
        _logger.warning(
            "No answer for the %s earner; it earns nothing today", item.label
        )
    units = _units(answers.get(item.name))
    count = units or 0
    return Term(
        earner=item,
        answer=units,
        gaming_minutes=item.gaming_for(count),
        shutdown_minutes=item.shutdown_for(count, day),
    )


def _sick_or(earned: int, terms: list[Term], day: date) -> int:
    """A sick day's shutdown: 20:00 plus gaming pay, never below ``earned``."""
    return max(earned, sick_shutdown_from(sum(t.gaming_minutes for t in terms), day))


def resolve(
    answers: Mapping[str, Answer],
    day: date | None = None,
    earners: tuple[Earner, ...] | None = None,
    *,
    first_credits: Mapping[str, date | None] | None = None,
    sick: bool = False,
    leisure: bool = False,
) -> Resolution:
    """Sum the base and every earned term, each capped at its ceiling.

    Args:
        answers: Per earner name, a unit count or ``None`` ("could not check").
            A registered earner missing from it earns nothing and is logged:
            the consumer forgot to ask, which must not pass as a "no".
        day: The day to resolve (default today): it picks the registry, the
            base, the ceiling, and (on the ladder) each earner's minutes.
        earners: The registry (default :func:`earners_for` the day); tests
            pass their own. An answer for an earner registered on other days
            only (Anki after ``TUTOR_FROM``) is ignored.
        first_credits: Per earner name, its first real credit day (``None``
            for never, or could not check), e.g. ``Maturity.first_credit``.
            Only ever delays a penalty; omitted, 0.5.0's ``penalty_from``.
        sick: The day is a sick day (the consumer asks ``sickdays``): shutdown
            is 20:00 plus the terms' gaming pay
            (:func:`~earned_time._sick.sick_shutdown_from`, 0.13.0).
            Gaming and every term are unchanged.
        leisure: Price gaming as if ``LEISURE_FROM`` had passed (0.14.0): the
            leisure base and cap whatever the day -- the shadow budget.
            Terms, penalties and shutdown are unchanged.

    Returns:
        The resolution, with a term for every registered earner.

    Raises:
        KeyError: ``answers`` names an earner that is not registered -- a
            typo that would otherwise silently earn nothing.
    """
    target = day or _today()
    registry = earners_for(target) if earners is None else earners
    _check_registered(answers, registry)
    base = base_for(target, registry, first_credits=first_credits, leisure=leisure)
    terms = [_term(item, answers, target) for item in registry]
    gaming = base.gaming_minutes + sum(t.gaming_minutes for t in terms)
    earned = min(
        shutdown_ceiling_for(target),
        base.shutdown_minutes + sum(t.shutdown_minutes for t in terms),
    )
    shutdown = _sick_or(earned, terms, target) if sick else earned
    return Resolution(
        day=target,
        base=base,
        terms=tuple(terms),
        gaming_minutes=min(
            gaming_ceiling_minutes_for(leisure_day(target, leisure=leisure)), gaming
        ),
        shutdown_minutes=shutdown,
        sick=sick,
        sick_lift_minutes=shutdown - earned,
    )
