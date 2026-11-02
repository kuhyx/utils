# Copyright (c) 2026 Krzysztof Rudnicki
"""The focus project (0.19.0): replaced gates stand down, one earner pays."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import importlib
import logging
from typing import Any, Final

from earned_time._ladder import shutdown_units_minutes
from earned_time._match import focus_match
from earned_time._policy import Earner

__all__ = [
    "FOCUS_LEDGER",
    "FOCUS_WATCH",
    "FocusEarner",
    "focus_earner",
    "with_focus",
]

FOCUS_LEDGER: Final = ".local/share/focus_project/ledger.json"
_SYNONYMS: Final = {"book": "reading"}
_logger: Final = logging.getLogger(__name__)
_warned: set[str] = set()


@dataclass(frozen=True)
class FocusEarner(Earner):
    """Counted; ``gaming_minutes``/``shutdown_minutes`` pay a FULL day.

    ``cut_gaming_minutes``: the gaming base cut, all the replaced gates paid,
    LeetCode's free hour too (0.20.0). The full-day gaming pay adds that free
    hour once more, so a full day matches the old one (kuhy 2026-11-02, 0.21.0).
    """

    cut_gaming_minutes: int = 0

    def gaming_for(self, units: int) -> int:
        """Gaming minutes of ``units`` focused minutes, floored."""
        return self.capped(units) * self.gaming_minutes // (self.max_units or 1)

    def shutdown_for(
        self,
        units: int,
        day: date | None = None,  # noqa: ARG002
    ) -> int:
        """Shutdown minutes of ``units`` focused minutes, floored."""
        return self.capped(units) * self.shutdown_minutes // (self.max_units or 1)


def _active(day: date) -> Any:  # noqa: ANN401
    """The active project on ``day``; ``None`` for none or on any failure."""
    try:
        return importlib.import_module("focus_project").active(day)
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        message = f"focus_project unusable ({type(exc).__name__}: {exc})"
        if message not in _warned:
            _warned.add(message)
            _logger.warning("%s; behaving as if no project is active", message)
        return None


def daily_on(project: Any, day: date) -> int:  # noqa: ANN401
    """``day``'s target: ``project.daily_on(day)`` (a later edit never re-prices it)."""
    pick = getattr(project, "daily_on", None)
    return int(pick(day) if pick is not None else project.daily_minutes)


def focus_earner(project: Any, dropped: tuple[Earner, ...], day: date) -> Earner:  # noqa: ANN401
    """The ``focus`` earner paying what ``dropped`` paid, over ``project``.

    Gaming: the cut is every dropped gate's full pay; a full day pays that plus
    the pure bonuses (no ``penalty_from``) again: 180 + 60 = 240 at 120 min.
    """
    cut = sum(e.max_gaming_minutes for e in dropped)
    free = tuple(e for e in dropped if e.penalty_from is None)
    return FocusEarner(
        name="focus",
        label="Focus",
        gaming_minutes=cut + sum(e.max_gaming_minutes for e in free),
        cut_gaming_minutes=cut,
        shutdown_minutes=sum(
            shutdown_units_minutes(e, e.max_units or 1, day) for e in dropped
        ),
        kind="counted",
        max_units=daily_on(project, day),
        penalty_from=project.start,
        confirmed_on=project.start - timedelta(days=1),
        ledger=FOCUS_LEDGER,
        match=focus_match,
        missing_ledger_is_no=True,
    )


FOCUS_WATCH: Final = FocusEarner(
    name="focus",
    label="Focus",
    gaming_minutes=0,
    shutdown_minutes=0,
    kind="counted",
    max_units=1,
    ledger=FOCUS_LEDGER,
    match=focus_match,
    missing_ledger_is_no=True,
)


def with_focus(registry: tuple[Earner, ...], day: date) -> tuple[Earner, ...]:
    """``registry`` reshaped by the active project; unchanged if none."""
    project = _active(day)
    if project is None:
        return registry
    gates = {_SYNONYMS.get(g, g) for g in project.replaces}
    dropped = tuple(e for e in registry if e.name in gates)
    if not dropped or daily_on(project, day) < 1:
        return registry
    kept = tuple(e for e in registry if e not in dropped)
    return (*kept, focus_earner(project, dropped, day))
