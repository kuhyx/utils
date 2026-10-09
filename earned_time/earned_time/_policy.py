# Copyright (c) 2026 Krzysztof Rudnicki
"""The one table of what every gate earns: the earner registry and the bases.

Every number that used to be duplicated between screen-locker (shutdown) and
steam-backlog-enforcer (gaming) lives here, once. A consumer never hard-codes
an hour; it asks :func:`earned_time.resolve` and applies the answer.

**Penalty, then reward.** A gate with ``penalty_from`` lowers the base by
exactly what it pays back, from that day on. Doing the thing restores the old
day; skipping it costs the full amount. The date is the gate's own start, so
the cut never lands before the reward that pays for it -- taking an hour a
reader could not yet earn back was a same-day loss on 2026-09-26.

**Ceilings stay put.** Adding a penalised earner leaves the best case
unchanged: the base drops by what the new earner adds.

From ``LADDER_FROM`` shutdown follows the sleep ladder instead
(:mod:`earned_time._ladder`); gaming keeps the penalty derivation unchanged.

**The registry is per day** (:func:`earners_for`). From ``TUTOR_FROM`` Anki
is retired -- neither penalised nor paid -- and Automation is the tutor's
counted earner; every earlier day resolves on :data:`EARNERS` exactly as
before, so the cutover never rewrites an old day.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Final, Literal

from earned_time._ladder import TUTOR_FROM, shutdown_units_minutes
from earned_time._match import (
    anki_match,
    leetcode_match,
    reading_match,
    tutor_match,
    workout_match,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    Window = tuple[float, float]
    # Whether one HMAC-verified ``credit`` row counts for the window.
    CreditMatch = Callable[[dict[str, object], Window], bool]

# The day before any earner's penalty: 5h of gaming, shutdown at 20:00.
# Minutes, both of them -- shutdown is minutes after local midnight.
GAMING_BASE_MINUTES: Final = 5 * 60
SHUTDOWN_BASE_MINUTES: Final = 20 * 60

# Hard ceilings, whatever the terms add up to.
GAMING_CEILING_MINUTES: Final = 8 * 60


@dataclass(frozen=True)
class Earner:
    """One gate's reward, and (optionally) the base cut that comes with it.

    Attributes:
        name: Registry key. screen-locker stamps its live pass as
            ``f"{name}_bonus_date"``, so renaming an earner re-applies its
            bonus once.
        label: Human name, for logs and reason strings.
        gaming_minutes: Gaming time the first unit earns.
        shutdown_minutes: How much later shutdown moves for the first unit.
        kind: ``"flat"`` earns once per day from a yes/no answer;
            ``"counted"`` earns per unit (the workout), and its live credit is
            applied by the consumer that counts the units.
        extra_shutdown_minutes: Each further unit, for ``"counted"`` earners.
        extra_gaming_minutes: Gaming time each further unit earns
            (``"counted"``); the workout's are 0, the tutor's 15.
        max_units: The most units one day can pay; ``None`` is unbounded.
        penalty_from: From this day the gaming base drops by the most the
            earner can pay (:attr:`max_gaming_minutes`). ``None`` means a pure
            bonus.
        ledger: The gate's HMAC-signed ledger, relative to the home directory.
            ``None`` means no shared reader: the consumer supplies the answer.
        match: Which verified ``credit`` rows count for today.
        missing_ledger_is_no: A ledger that does not exist yet is an honest
            "no" (the gate never ran), not a fault.
        confirmed_on: The day kuhy confirmed a real working session; set by
            hand, never derived. ``None`` keeps the gate "new"
            (:func:`earned_time.maturity`).

    ``shutdown_minutes`` and ``extra_shutdown_minutes`` are the pre-ladder
    values; from ``LADDER_FROM`` the earner's :class:`Rung` in ``LADDER``
    applies (:func:`shutdown_minutes_for`).
    """

    name: str
    label: str
    gaming_minutes: int
    shutdown_minutes: int
    kind: Literal["flat", "counted"] = "flat"
    extra_shutdown_minutes: int = 0
    penalty_from: date | None = None
    ledger: str | None = None
    match: CreditMatch | None = None
    missing_ledger_is_no: bool = False
    extra_gaming_minutes: int = 0
    max_units: int | None = None
    confirmed_on: date | None = None

    def capped(self, units: int) -> int:
        """``units`` clamped to ``[0, max_units]``."""
        units = max(0, units)
        return units if self.max_units is None else min(units, self.max_units)

    @property
    def max_gaming_minutes(self) -> int:
        """Gaming time a fully done day earns: what the penalty takes off."""
        return self.gaming_for(self.max_units or 1)

    def penalised_on(self, day: date) -> bool:
        """Whether this earner's base cut is in force on ``day``."""
        return self.penalty_from is not None and day >= self.penalty_from

    def gaming_for(self, units: int) -> int:
        """Gaming minutes ``units`` earn, capped at ``max_units``."""
        count = self.capped(units)
        if not count:
            return 0
        return self.gaming_minutes + (count - 1) * self.extra_gaming_minutes

    def shutdown_for(self, units: int, day: date | None = None) -> int:
        """Shutdown minutes ``units`` earn on ``day`` (default today)."""
        target = day or datetime.now(tz=UTC).astimezone().date()
        return shutdown_units_minutes(self, self.capped(units), target)


WORKOUT: Final = Earner(
    name="workout",
    label="workout",
    gaming_minutes=2 * 60,
    shutdown_minutes=2 * 60,
    kind="counted",
    extra_shutdown_minutes=60,
    # screen-locker writes one signed row per credited unit (a verified
    # RunnerUp TCX, or a rest day); ``credit_units`` counts them.
    ledger=".local/share/workout_locker/ledger.json",
    match=workout_match,
    missing_ledger_is_no=True,
    # The day of its first verified credit, read off the real ledger on
    # 2026-10-09 (earned_time 0.6.0); kuhy had been using the gate for real.
    confirmed_on=date(2026, 10, 1),
)
LEETCODE: Final = Earner(
    name="leetcode",
    label="LeetCode",
    gaming_minutes=60,
    shutdown_minutes=60,
    ledger=".local/share/leetcode_guard/ledger.json",
    match=leetcode_match,
    # The day of its first verified credit, read off the real ledger on
    # 2026-10-09 (earned_time 0.6.0); kuhy had been using the gate for real.
    confirmed_on=date(2026, 8, 12),
)
READING: Final = Earner(
    name="reading",
    label="reading",
    gaming_minutes=60,
    shutdown_minutes=60,
    penalty_from=date(2026, 10, 1),
    ledger=".local/share/book_guard/ledger.json",
    match=reading_match,
    missing_ledger_is_no=True,
    # The day of its first verified credit, read off the real ledger on
    # 2026-10-09 (earned_time 0.6.0); kuhy had been using the gate for real.
    confirmed_on=date(2026, 10, 2),
)
ANKI: Final = Earner(
    name="anki",
    label="Anki",
    gaming_minutes=30,
    shutdown_minutes=30,
    penalty_from=date(2026, 10, 6),
    ledger=".local/share/anki_guard/ledger.json",
    match=anki_match,
    missing_ledger_is_no=True,
)
# Same gate, same row shape: anki-guard's ``automation`` quota (the Automation
# deck only) writes its own ledger, so the Anki day matcher applies unchanged.
# Days before ``TUTOR_FROM`` only; from then on see AUTOMATION_TUTOR.
AUTOMATION: Final = Earner(
    name="automation",
    label="Automation",
    gaming_minutes=30,
    shutdown_minutes=30,
    penalty_from=date(2026, 10, 6),
    ledger=".local/share/anki_guard/automation_ledger.json",
    match=anki_match,
    missing_ledger_is_no=True,
)

# From ``TUTOR_FROM``: the Automation tutor pays per verified 15-minute block,
# up to four a day. Anki's 30 gaming minutes are folded in (4 x 15 = 60), so
# retiring Anki is not a free +30: the base drops by the full 60.
AUTOMATION_TUTOR: Final = Earner(
    name="automation",
    label="Automation",
    gaming_minutes=15,
    extra_gaming_minutes=15,
    max_units=4,
    # Pre-ladder values, unused (TUTOR_FROM is not before LADDER_FROM); the
    # ladder pays 13/13/12/12 (``TUTOR_LADDER``).
    shutdown_minutes=13,
    extra_shutdown_minutes=13,
    kind="counted",
    penalty_from=TUTOR_FROM,
    ledger=".local/share/automation_tutor/ledger.json",
    match=tutor_match,
    missing_ledger_is_no=True,
)

# The registry of every day before ``TUTOR_FROM``. Order is the order of
# reason strings and of screen-locker's live pass.
EARNERS: Final[tuple[Earner, ...]] = (
    WORKOUT,
    LEETCODE,
    READING,
    ANKI,
    AUTOMATION,
)
# From ``TUTOR_FROM``: Anki retired, Automation paid per tutor block.
TUTOR_EARNERS: Final[tuple[Earner, ...]] = (
    WORKOUT,
    LEETCODE,
    READING,
    AUTOMATION_TUTOR,
)


def earner(name: str, earners: tuple[Earner, ...] = EARNERS) -> Earner:
    """Look an earner up by name.

    Raises:
        KeyError: No earner is registered under ``name``.
    """
    for candidate in earners:
        if candidate.name == name:
            return candidate
    raise KeyError(name)
