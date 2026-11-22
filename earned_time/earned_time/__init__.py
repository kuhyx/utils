# Copyright (c) 2026 Krzysztof Rudnicki
"""Penalty-then-reward for gate apps: one registry, one sum, two consumers.

A gate (leetcode-guard, book-guard, ...) never touches gaming time or the
shutdown schedule. It publishes a fact -- HMAC-signed ``credit`` rows in its
ledger -- and registers one :class:`Earner` here. The two consumers read the
registry and apply the result:

* steam-backlog-enforcer enforces ``Resolution.gaming_minutes``;
* screen-locker writes ``Resolution.shutdown_minutes`` to the schedule.

A consumer's whole integration::

    import earned_time

    answers = {
        e.name: earned_time.done_today(e, home / e.ledger, KEY_FILE)
        for e in earned_time.EARNERS
        if e.ledger is not None
    }
    answers["workout"] = my_workout_count()
    day = earned_time.resolve(answers, sick=sickdays.is_sick_day())
    apply(day.gaming_minutes)

``gaming_enforced(day)`` (0.22.0): from ``GAMING_UNLIMITED_FROM`` there is no
gaming budget; shutdown is the only carrot. ``Resolution.gaming_enforced``
carries it; a consumer that applies a budget lifts the limit on ``False``.

``progress`` (0.24.0): a gate signs "done N of M"; ``progress_map(day, home,
key_file)`` reads it, ``resolve(..., progress=...)`` pays a no that share of a
yes (``DOCS-progress.md``). No row anywhere resolves exactly as 0.23.0.

``sick`` (0.11.0) only raises shutdown to at least 20:00; gaming is unchanged.
``leisure`` (0.16.0): ``None`` follows the switch file on ``day``, ``True``
prices gaming with the leisure base and cap (the shadow budget), ``False``
with the old ones. The first real leisure day is :func:`leisure_from`
(0.15.0, the switch file); ask :func:`leisure_active` for the gaming day.

How far to trust a gate is computed, not listed: :func:`maturity` (and
``python -m earned_time maturity``).

Adding a gate is one :class:`Earner` in :mod:`earned_time._policy`; with
``penalty_from`` set, the base drops by what it pays back from that day on.
"""

from __future__ import annotations

from earned_time._credits import (
    credit_units,
    day_window,
    first_credit_at,
)
from earned_time._evidence import real_credit
from earned_time._focus import FOCUS_LEDGER, FocusEarner
from earned_time._gaming import GAMING_UNLIMITED_FROM, gaming_enforced
from earned_time._ladder import (
    ANKI_WAIVED_FROM,
    LADDER,
    LADDER_FROM,
    SHUTDOWN_CEILING_MINUTES,
    TUTOR_FROM,
    TUTOR_LADDER,
    UNIFIED_FROM,
    UNIFIED_LADDER,
    WAKE_MINUTES,
    Rung,
    extra_shutdown_minutes_for,
    ladder_for,
    on_ladder,
    shutdown_ceiling_for,
    shutdown_minutes_for,
)
from earned_time._ledger import done_today, entry_signature, today_window, verified
from earned_time._leisure import (
    LEISURE_BASE_MINUTES,
    LEISURE_CEILING_MINUTES,
    LEISURE_FROM,
    LEISURE_FROM_PATH,
    gaming_base_minutes_for,
    gaming_ceiling_minutes_for,
    leisure_active,
    leisure_from,
)
from earned_time._maturity import (
    MATURE_MIN_AGE_DAYS,
    MATURE_MIN_CREDIT_DAYS,
    Level,
    Maturity,
    confirmed_start,
    maturity,
    penalty_start,
)
from earned_time._policy import (
    ANKI,
    AUTOMATION,
    EARNERS,
    GAMING_BASE_MINUTES,
    GAMING_CEILING_MINUTES,
    LEETCODE,
    READING,
    SHUTDOWN_BASE_MINUTES,
    TUTOR,
    TUTOR_EARNERS,
    WORKOUT,
    Earner,
    earner,
)
from earned_time._progress import Progress, progress_map, read_progress
from earned_time._quota import TUTOR_QUOTA_FROM, TUTOR_QUOTA_MINUTES, tutor_quota_for
from earned_time._registry import all_earners, earners_for, registries
from earned_time._resolve import Base, Resolution, Term, base_for, resolve
from earned_time._review import (
    ACCEPTED_LOOKBACK_DAYS,
    GUARD_LEDGER,
    REVIEW,
    REVIEW_FROM,
    REVIEW_LEDGER,
    REVIEW_SHUTDOWN_MINUTES,
    REVIEW_SOURCE,
    guard_ledger_for,
    paid_reviews,
    review_match,
)
from earned_time._sick import SICK_SHUTDOWN_FLOOR_MINUTES, sick_shutdown_from

__all__ = [
    "ACCEPTED_LOOKBACK_DAYS",
    "ANKI",
    "ANKI_WAIVED_FROM",
    "AUTOMATION",
    "EARNERS",
    "FOCUS_LEDGER",
    "GAMING_BASE_MINUTES",
    "GAMING_CEILING_MINUTES",
    "GAMING_UNLIMITED_FROM",
    "GUARD_LEDGER",
    "LADDER",
    "LADDER_FROM",
    "LEETCODE",
    "LEISURE_BASE_MINUTES",
    "LEISURE_CEILING_MINUTES",
    "LEISURE_FROM",
    "LEISURE_FROM_PATH",
    "MATURE_MIN_AGE_DAYS",
    "MATURE_MIN_CREDIT_DAYS",
    "READING",
    "REVIEW",
    "REVIEW_FROM",
    "REVIEW_LEDGER",
    "REVIEW_SHUTDOWN_MINUTES",
    "REVIEW_SOURCE",
    "SHUTDOWN_BASE_MINUTES",
    "SHUTDOWN_CEILING_MINUTES",
    "SICK_SHUTDOWN_FLOOR_MINUTES",
    "TUTOR",
    "TUTOR_EARNERS",
    "TUTOR_FROM",
    "TUTOR_LADDER",
    "TUTOR_QUOTA_FROM",
    "TUTOR_QUOTA_MINUTES",
    "UNIFIED_FROM",
    "UNIFIED_LADDER",
    "WAKE_MINUTES",
    "WORKOUT",
    "Base",
    "Earner",
    "FocusEarner",
    "Level",
    "Maturity",
    "Progress",
    "Resolution",
    "Rung",
    "Term",
    "all_earners",
    "base_for",
    "confirmed_start",
    "credit_units",
    "day_window",
    "done_today",
    "earner",
    "earners_for",
    "entry_signature",
    "extra_shutdown_minutes_for",
    "first_credit_at",
    "gaming_base_minutes_for",
    "gaming_ceiling_minutes_for",
    "gaming_enforced",
    "guard_ledger_for",
    "ladder_for",
    "leisure_active",
    "leisure_from",
    "maturity",
    "on_ladder",
    "paid_reviews",
    "penalty_start",
    "progress_map",
    "read_progress",
    "real_credit",
    "registries",
    "resolve",
    "review_match",
    "shutdown_ceiling_for",
    "shutdown_minutes_for",
    "sick_shutdown_from",
    "today_window",
    "tutor_quota_for",
    "verified",
]
