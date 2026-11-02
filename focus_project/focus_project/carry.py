# Copyright (c) 2026 Krzysztof Rudnicki
"""Overtime carries over: minutes past a day's target bank for the next day.

Contract (kuhy, 2026-11-02): own minutes beyond ``daily_on(day)`` are banked
(at most :data:`BANK_CAP`) and pay on the NEXT project day. The bank never
crosses the project's last day (what is left then expires) and a carry never
pays on a day with no project. The balance is derived from the activity
record, never stored, so it cannot drift; a project day's counted minutes
are ``min(daily, own + carried_in)``. The bank is spent first, so what a day
takes from it is fixed when the day starts and only own minutes grow.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import logging
from typing import Final

from focus_project import _api, _clock
from focus_project._errors import RegistryError
from focus_project._own import own_minutes_of

BANK_CAP: Final = 60
_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class Balance:
    """One project day: worked minutes, bank taken in, bank left for tomorrow."""

    own: int
    carried_in: int
    carry_out: int

    def paid_bank(self, daily: int) -> int:
        """Minutes of the day paid from the bank (fixed at the day's start)."""
        return min(self.carried_in, daily)

    def paid_own(self, daily: int) -> int:
        """Minutes of the day paid from own work, after the bank."""
        return min(self.own, daily - self.paid_bank(daily))

    def counted(self, daily: int) -> int:
        """Minutes that count on the day: own plus carried, capped at ``daily``."""
        return min(daily, self.own + self.carried_in)


_NONE: Final = Balance(0, 0, 0)


def balance(day: date, now: float | None = None) -> Balance:
    """The balance of ``day`` (zeros with no project or an unreadable registry)."""
    moment = _clock.now() if now is None else now
    try:
        project = _api.active(day)
        if project is None:
            return _NONE
        bank = 0
        cursor = project.start
        while True:
            own = own_minutes_of(project, cursor, moment)
            total = own + bank
            left = min(BANK_CAP, max(0, total - project.daily_on(cursor)))
            if cursor >= day:
                return Balance(own, bank, left)
            bank, cursor = left, cursor + timedelta(days=1)
    except (RegistryError, OSError) as exc:
        _LOG.warning("focus_project registry unreadable, nothing banked: %s", exc)
        return _NONE


def own_minutes(day: date, now: float | None = None) -> int:
    """Minutes worked on ``day``, not capped at the target (0 with no project)."""
    return balance(day, now).own
