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

from earned_time._floor import gaming_cut, is_penalised, shutdown_floor
from earned_time._gaming import gaming_enforced
from earned_time._ladder import shutdown_ceiling_for
from earned_time._leisure import base_minutes, ceiling_minutes, is_leisure
from earned_time._registry import all_earners, earners_for
from earned_time._resolution import Base, Resolution, Term
from earned_time._share import gaming_share, shutdown_share
from earned_time._sick import sick_or

if TYPE_CHECKING:
    from collections.abc import Mapping

    from earned_time._policy import Earner
    from earned_time._progress import Progress

_logger: Final = logging.getLogger(__name__)

Answer = int | bool | None


def _today() -> date:
    return datetime.now(tz=UTC).astimezone().date()


def base_for(
    day: date | None = None,
    earners: tuple[Earner, ...] | None = None,
    *,
    first_credits: Mapping[str, date | None] | None = None,
    leisure: bool | None = None,
) -> Base:
    """The floor for ``day`` (default today) under ``earners`` (default its own).

    Gaming: every penalty in force, the most each earner can pay, taken off
    the gaming base. Shutdown: see ``_floor.shutdown_floor`` -- the two are
    derived separately so the ladder can never move a gaming minute.
    ``first_credits`` (per earner name) delays each penalty, and the ladder
    rung, to :func:`penalty_start`; omitted, 0.5.0's ``penalty_from`` applies.
    The gaming base: ``leisure`` ``None`` -- by the switch file on the day,
    ``True``/``False`` -- the leisure/old base whatever the date
    (:func:`is_leisure`).
    """
    target = day or _today()
    registry = earners_for(target) if earners is None else earners
    on = is_leisure(target, leisure=leisure)
    return _base(target, registry, first_credits, on=on)


def _base(
    target: date,
    registry: tuple[Earner, ...],
    first_credits: Mapping[str, date | None] | None,
    *,
    on: bool,
) -> Base:
    penalised = [e for e in registry if is_penalised(e, target, first_credits)]
    return Base(
        gaming_minutes=base_minutes(leisure=on) - sum(gaming_cut(e) for e in penalised),
        shutdown_minutes=shutdown_floor(target, registry, penalised),
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


def _term(
    item: Earner,
    answers: Mapping[str, Answer],
    day: date,
    progress: Mapping[str, Progress] | None,
) -> Term:
    """``item``'s term on ``day``; no answer at all is logged and earns nothing.

    Progress pays only a no (``0``/``False``): a yes pays in full as ever and
    ``None`` ("could not check") earns nothing, row or no row.
    """
    if item.name not in answers:
        _logger.warning(
            "No answer for the %s earner; it earns nothing today", item.label
        )
    units = _units(answers.get(item.name))
    no = units is not None and units < 1
    share = (progress or {}).get(item.name) if no else None
    if share is not None:
        return Term(
            item,
            units,
            gaming_share(item, share),
            shutdown_share(item, share, day),
            share,
        )
    count = units or 0
    return Term(
        earner=item,
        answer=units,
        gaming_minutes=item.gaming_for(count),
        shutdown_minutes=item.shutdown_for(count, day),
    )


def resolve(
    answers: Mapping[str, Answer],
    day: date | None = None,
    earners: tuple[Earner, ...] | None = None,
    *,
    first_credits: Mapping[str, date | None] | None = None,
    sick: bool = False,
    leisure: bool | None = None,
    progress: Mapping[str, Progress] | None = None,
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
            (:func:`~earned_time._sick.sick_shutdown_from`, 0.13.0), from
            ``GAMING_UNLIMITED_FROM`` their shutdown pay (0.22.0).
            Gaming and every term are unchanged.
        leisure: ``None`` (0.16.0 default): the switch file decides on
            ``day``. ``True`` (0.14.0): the leisure base and cap whatever the
            day says -- the shadow budget. ``False``: the old base and cap
            whatever the file says -- a gaming day (06:00) still before the
            switch while the calendar day is past it. Terms, penalties and
            shutdown are unchanged. From ``GAMING_UNLIMITED_FROM`` (0.22.0)
            ``None`` is always the old base: read
            ``Resolution.gaming_enforced``, the budget is not a limit.
        progress: Per earner name, its signed progress (0.24.0,
            :func:`~earned_time.progress_map`). A term uses it only when its
            answer is ``0``/``False``, and then pays that share of a yes; a
            true answer pays full and ``None`` nothing. Omitted: 0.23.0 exactly.

    Returns:
        The resolution, with a term for every registered earner.

    Raises:
        KeyError: ``answers`` names an earner that is not registered -- a
            typo that would otherwise silently earn nothing.
    """
    target = day or _today()
    registry = earners_for(target) if earners is None else earners
    _check_registered(answers, registry)
    # One switch-file read per resolve, so base and cap can never disagree.
    on = is_leisure(target, leisure=leisure)
    base = _base(target, registry, first_credits, on=on)
    terms = [_term(item, answers, target, progress) for item in registry]
    gaming = base.gaming_minutes + sum(t.gaming_minutes for t in terms)
    earned = min(
        shutdown_ceiling_for(target),
        base.shutdown_minutes + sum(t.shutdown_minutes for t in terms),
    )
    shutdown = sick_or(earned, terms, target) if sick else earned
    return Resolution(
        day=target,
        base=base,
        terms=tuple(terms),
        gaming_minutes=min(ceiling_minutes(leisure=on), gaming),
        shutdown_minutes=shutdown,
        sick=sick,
        sick_lift_minutes=shutdown - earned,
        gaming_enforced=gaming_enforced(target),
    )
