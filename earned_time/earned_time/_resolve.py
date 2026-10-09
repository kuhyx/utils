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
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
import logging
from typing import TYPE_CHECKING, Final

from earned_time._ladder import on_ladder, shutdown_ceiling_for
from earned_time._policy import (
    GAMING_BASE_MINUTES,
    GAMING_CEILING_MINUTES,
    SHUTDOWN_BASE_MINUTES,
    Earner,
)
from earned_time._registry import all_earners, earners_for

if TYPE_CHECKING:
    from collections.abc import Mapping

_logger: Final = logging.getLogger(__name__)

Answer = int | bool | None


@dataclass(frozen=True)
class Base:
    """The floor for one day, after every penalty in force on it.

    Attributes:
        gaming_minutes: Gaming time a day that earned nothing gets.
        shutdown_minutes: Shutdown time of such a day, minutes after midnight.
    """

    gaming_minutes: int
    shutdown_minutes: int


@dataclass(frozen=True)
class Term:
    """What one earner contributed.

    Attributes:
        earner: The earner.
        answer: The consumer's answer: a unit count, or ``None`` for
            "could not check" (and for no answer at all).
        gaming_minutes: Gaming minutes earned.
        shutdown_minutes: Shutdown minutes earned.
    """

    earner: Earner
    answer: int | None
    gaming_minutes: int
    shutdown_minutes: int


@dataclass(frozen=True)
class Resolution:
    """One day's budget and shutdown, and what earned them.

    Attributes:
        day: The day resolved.
        base: Its floor.
        terms: One entry per registered earner, in registry order.
        gaming_minutes: Base plus terms, capped at the gaming ceiling.
        shutdown_minutes: Base plus terms, capped at the shutdown ceiling.
    """

    day: date
    base: Base
    terms: tuple[Term, ...]
    gaming_minutes: int
    shutdown_minutes: int

    def term(self, name: str) -> Term:
        """The term of the earner called ``name``.

        Raises:
            KeyError: No such earner was resolved.
        """
        for candidate in self.terms:
            if candidate.earner.name == name:
                return candidate
        raise KeyError(name)


def _today() -> date:
    return datetime.now(tz=UTC).astimezone().date()


def _shutdown_floor(day: date, earners: tuple[Earner, ...]) -> int:
    """Shutdown of a day that earned nothing.

    On the ladder: the ceiling minus the most every registered earner can
    pay (all of a capped earner's units), so doing everything lands exactly
    on the ceiling. Before it: the old base minus the penalties in force.
    """
    if on_ladder(day):
        return shutdown_ceiling_for(day) - sum(
            e.shutdown_for(e.max_units or 1, day) for e in earners
        )
    penalised = [e for e in earners if e.penalised_on(day)]
    return SHUTDOWN_BASE_MINUTES - sum(e.shutdown_minutes for e in penalised)


def base_for(
    day: date | None = None, earners: tuple[Earner, ...] | None = None
) -> Base:
    """The floor for ``day`` (default today) under ``earners`` (default its own).

    Gaming: every penalty in force, the most each earner can pay, taken off
    the gaming base. Shutdown: see :func:`_shutdown_floor` -- the two are
    derived separately so the ladder can never move a gaming minute.
    """
    target = day or _today()
    registry = earners_for(target) if earners is None else earners
    penalised = [e for e in registry if e.penalised_on(target)]
    return Base(
        gaming_minutes=GAMING_BASE_MINUTES
        - sum(e.max_gaming_minutes for e in penalised),
        shutdown_minutes=_shutdown_floor(target, registry),
    )


def _units(answer: Answer) -> int | None:
    if answer is None:
        return None
    return max(0, int(answer))


def resolve(
    answers: Mapping[str, Answer],
    day: date | None = None,
    earners: tuple[Earner, ...] | None = None,
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

    Returns:
        The resolution, with a term for every registered earner.

    Raises:
        KeyError: ``answers`` names an earner that is not registered -- a
            typo that would otherwise silently earn nothing.
    """
    target = day or _today()
    registry = earners_for(target) if earners is None else earners
    known = {e.name for e in (*registry, *all_earners())}
    unknown = sorted(set(answers) - known)
    if unknown:
        msg = f"not registered earners: {', '.join(unknown)}"
        raise KeyError(msg)
    base = base_for(target, registry)
    terms: list[Term] = []
    for item in registry:
        if item.name not in answers:
            _logger.warning(
                "No answer for the %s earner; it earns nothing today", item.label
            )
        units = _units(answers.get(item.name))
        count = units or 0
        terms.append(
            Term(
                earner=item,
                answer=units,
                gaming_minutes=item.gaming_for(count),
                shutdown_minutes=item.shutdown_for(count, target),
            )
        )
    gaming = base.gaming_minutes + sum(t.gaming_minutes for t in terms)
    shutdown = base.shutdown_minutes + sum(t.shutdown_minutes for t in terms)
    return Resolution(
        day=target,
        base=base,
        terms=tuple(terms),
        gaming_minutes=min(GAMING_CEILING_MINUTES, gaming),
        shutdown_minutes=min(shutdown_ceiling_for(target), shutdown),
    )
