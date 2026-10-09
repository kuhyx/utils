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
    day = earned_time.resolve(answers)
    apply(day.gaming_minutes)

Adding a gate is one :class:`Earner` in :mod:`earned_time._policy`; with
``penalty_from`` set, the base drops by what it pays back from that day on.
"""

from __future__ import annotations

from earned_time._credits import (
    credit_units,
    day_window,
    first_credit_at,
)
from earned_time._ladder import (
    ANKI_WAIVED_FROM,
    LADDER,
    LADDER_FROM,
    SHUTDOWN_CEILING_MINUTES,
    TUTOR_FROM,
    TUTOR_LADDER,
    WAKE_MINUTES,
    Rung,
    extra_shutdown_minutes_for,
    ladder_for,
    on_ladder,
    shutdown_ceiling_for,
    shutdown_minutes_for,
)
from earned_time._ledger import done_today, entry_signature, today_window, verified
from earned_time._policy import (
    ANKI,
    AUTOMATION,
    AUTOMATION_TUTOR,
    EARNERS,
    GAMING_BASE_MINUTES,
    GAMING_CEILING_MINUTES,
    LEETCODE,
    READING,
    SHUTDOWN_BASE_MINUTES,
    TUTOR_EARNERS,
    WORKOUT,
    Earner,
    earner,
)
from earned_time._registry import all_earners, earners_for, registries
from earned_time._resolve import Base, Resolution, Term, base_for, resolve

__all__ = [
    "ANKI",
    "ANKI_WAIVED_FROM",
    "AUTOMATION",
    "AUTOMATION_TUTOR",
    "EARNERS",
    "GAMING_BASE_MINUTES",
    "GAMING_CEILING_MINUTES",
    "LADDER",
    "LADDER_FROM",
    "LEETCODE",
    "READING",
    "SHUTDOWN_BASE_MINUTES",
    "SHUTDOWN_CEILING_MINUTES",
    "TUTOR_EARNERS",
    "TUTOR_FROM",
    "TUTOR_LADDER",
    "WAKE_MINUTES",
    "WORKOUT",
    "Base",
    "Earner",
    "Resolution",
    "Rung",
    "Term",
    "all_earners",
    "base_for",
    "credit_units",
    "day_window",
    "done_today",
    "earner",
    "earners_for",
    "entry_signature",
    "extra_shutdown_minutes_for",
    "first_credit_at",
    "ladder_for",
    "on_ladder",
    "registries",
    "resolve",
    "shutdown_ceiling_for",
    "shutdown_minutes_for",
    "today_window",
    "verified",
]
