# Copyright (c) 2026 Krzysztof Rudnicki
"""Which registry is in force on a day: the tutor cutover (``TUTOR_FROM``).

Before ``TUTOR_FROM`` every day resolves on :data:`~earned_time.EARNERS`,
exactly as it always has; from it on :data:`~earned_time.TUTOR_EARNERS`
(Anki retired, Automation paid per tutor block). The switch is a date, so it
never rewrites how an old day resolved.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from functools import cache
import sys
from typing import TYPE_CHECKING, Final

from earned_time._ladder import ANKI_WAIVED_FROM, TUTOR_FROM

if TYPE_CHECKING:
    from earned_time._policy import Earner

# Waived from ``ANKI_WAIVED_FROM`` until ``TUTOR_FROM``.
_WAIVED: Final = frozenset({"anki", "automation"})


def registries() -> tuple[tuple[Earner, ...], ...]:
    """Every registry, oldest first.

    Read through the package, not this module: consumers' test suites patch
    ``earned_time.EARNERS`` to register a stand-in earner, and the patch must
    keep reaching :func:`earners_for` and :func:`all_earners`.
    """
    package = sys.modules["earned_time"]  # loaded: it imports this module
    return (package.EARNERS, package.TUTOR_EARNERS)


def earners_for(day: date | None = None) -> tuple[Earner, ...]:
    """The registry in force on ``day`` (default today).

    Between ``ANKI_WAIVED_FROM`` and ``TUTOR_FROM`` the old registry without
    Anki and the anki-backed Automation: neither penalised nor paid.
    """
    target = day or datetime.now(tz=UTC).astimezone().date()
    before, tutor = registries()
    if target >= TUTOR_FROM:
        return tutor
    if target >= ANKI_WAIVED_FROM:
        return _without_waived(before)
    return before


@cache
def _without_waived(registry: tuple[Earner, ...]) -> tuple[Earner, ...]:
    """``registry`` minus the waived earners; one stable tuple per registry."""
    return tuple(e for e in registry if e.name not in _WAIVED)


def all_earners() -> tuple[Earner, ...]:
    """Every earner of every registry, once each, oldest registry first.

    What a reader that must not miss a ledger across a cutover watches
    (screen-locker's path unit).
    """
    seen: dict[Earner, None] = {}
    for registry in registries():
        seen.update(dict.fromkeys(registry))
    return tuple(seen)
