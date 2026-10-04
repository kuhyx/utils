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
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
import logging
from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:
    from collections.abc import Callable

    Window = tuple[float, float]
    # Whether one HMAC-verified ``credit`` row counts for the window.
    CreditMatch = Callable[[dict[str, object], Window], bool]

_logger: Final = logging.getLogger(__name__)

# The day before any earner's penalty: 5h of gaming, shutdown at 20:00.
# Minutes, both of them -- shutdown is minutes after local midnight.
GAMING_BASE_MINUTES: Final = 5 * 60
SHUTDOWN_BASE_MINUTES: Final = 20 * 60

# Hard ceilings, whatever the terms add up to.
GAMING_CEILING_MINUTES: Final = 8 * 60
SHUTDOWN_CEILING_MINUTES: Final = 23 * 60


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
        penalty_from: From this day the base drops by ``gaming_minutes`` and
            ``shutdown_minutes``. ``None`` means a pure bonus.
        ledger: The gate's HMAC-signed ledger, relative to the home directory.
            ``None`` means no shared reader: the consumer supplies the answer.
        match: Which verified ``credit`` rows count for today.
        missing_ledger_is_no: A ledger that does not exist yet is an honest
            "no" (the gate never ran), not a fault.
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

    def penalised_on(self, day: date) -> bool:
        """Whether this earner's base cut is in force on ``day``."""
        return self.penalty_from is not None and day >= self.penalty_from

    def gaming_for(self, units: int) -> int:
        """Gaming minutes ``units`` earn: the first unit only, never more."""
        return self.gaming_minutes if units > 0 else 0

    def shutdown_for(self, units: int) -> int:
        """Shutdown minutes ``units`` earn: first unit, then each extra one."""
        if units <= 0:
            return 0
        return self.shutdown_minutes + (units - 1) * self.extra_shutdown_minutes


def _within(raw: object, window: Window) -> bool | None:
    """Whether a unix-seconds stamp falls in ``window``; ``None`` if unusable."""
    try:
        stamp = float(str(raw))
    except ValueError:
        return None
    start, end = window
    return start <= stamp <= end


def _leetcode_match(row: dict[str, object], window: Window) -> bool:
    """A solve counts on the day LeetCode accepted it (``submitted_at``).

    ``day`` is the *harvesting* run's date and runs late, so it is only the
    fallback for a row without a usable stamp: it can miss a late solve but
    never invent one.
    """
    detail = row.get("detail")
    raw = detail.get("submitted_at") if isinstance(detail, dict) else None
    if raw is not None:
        landed = _within(raw, window)
        if landed is not None:
            return landed
        _logger.warning(
            "LeetCode credit %r has an unparsable submitted_at (%r); "
            "falling back to its day key",
            row.get("entry_id"),
            raw,
        )
    local = datetime.fromtimestamp(window[0], tz=UTC).astimezone()
    return row.get("day") == local.date().isoformat()


def _reading_match(row: dict[str, object], window: Window) -> bool:
    """A reading credit counts if it earned the bonus and ended today."""
    detail = row.get("detail")
    if not isinstance(detail, dict) or detail.get("bonus") != "1":
        return False
    landed = _within(detail.get("ended_at"), window)
    if landed is None:
        _logger.warning("reading credit %r has no usable ended_at", row.get("entry_id"))
        return False
    return landed


WORKOUT: Final = Earner(
    name="workout",
    label="workout",
    gaming_minutes=2 * 60,
    shutdown_minutes=2 * 60,
    kind="counted",
    extra_shutdown_minutes=60,
)
LEETCODE: Final = Earner(
    name="leetcode",
    label="LeetCode",
    gaming_minutes=60,
    shutdown_minutes=60,
    ledger=".local/share/leetcode_guard/ledger.json",
    match=_leetcode_match,
)
READING: Final = Earner(
    name="reading",
    label="reading",
    gaming_minutes=60,
    shutdown_minutes=60,
    penalty_from=date(2026, 10, 1),
    ledger=".local/share/book_guard/ledger.json",
    match=_reading_match,
    missing_ledger_is_no=True,
)

# Order is the order of reason strings and of screen-locker's live pass.
EARNERS: Final[tuple[Earner, ...]] = (WORKOUT, LEETCODE, READING)


def earner(name: str, earners: tuple[Earner, ...] = EARNERS) -> Earner:
    """Look an earner up by name.

    Raises:
        KeyError: No earner is registered under ``name``.
    """
    for candidate in earners:
        if candidate.name == name:
            return candidate
    raise KeyError(name)
