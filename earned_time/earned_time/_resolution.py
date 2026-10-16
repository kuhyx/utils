# Copyright (c) 2026 Krzysztof Rudnicki
"""What :func:`earned_time.resolve` returns: the base, each term, the sum.

Split from :mod:`earned_time._resolve` (0.11.0) to keep both under the line
cap; ``earned_time._resolve`` still re-exports all three.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date

    from earned_time._policy import Earner


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
        shutdown_minutes: Base plus terms, capped at the shutdown ceiling;
            on a sick day raised to the sick floor (:mod:`earned_time._sick`).
        sick: Whether the day was resolved as a sick day (0.11.0).
        sick_lift_minutes: How far the sick floor raised ``shutdown_minutes``
            above base plus terms (``0`` unless sick): a consumer adding live
            credits on top pays them out of this first, as with a grace lift.
    """

    day: date
    base: Base
    terms: tuple[Term, ...]
    gaming_minutes: int
    shutdown_minutes: int
    sick: bool = False
    sick_lift_minutes: int = 0

    def term(self, name: str) -> Term:
        """The term of the earner called ``name``.

        Raises:
            KeyError: No such earner was resolved.
        """
        for candidate in self.terms:
            if candidate.earner.name == name:
                return candidate
        raise KeyError(name)
