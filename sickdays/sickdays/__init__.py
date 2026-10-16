# Copyright (c) 2026 Krzysztof Rudnicki
"""One shared pool of sick days that every gate respects.

A gate's whole integration::

    import sickdays

    if sickdays.is_sick_day(today):
        ...  # the sick-day rules for this gate apply

It reads one local file, never the network, and never raises: an unreadable
pool is logged and reads as "not sick", so the failure mode is "the normal
rules apply", never "everything is switched off".

Since 0.2.0 a sick day may keep some lockers active, so a gate that is one
of :data:`LOCKERS` asks the narrower question instead::

    if sickdays.stands_down(sickdays.LOCKER_LEETCODE):
        ...  # this locker is off today

Sick days are not free days. They are a separate pool, with a separate file
and a separate remote node, and a date is never in both
(:mod:`sickdays._conflict`). There is no cap and no justification: every day
is normal by default, and any day from today on can be marked or un-marked.
"""

from __future__ import annotations

from sickdays._api import (
    actor_id,
    add_sick_day,
    import_legacy,
    is_sick_day,
    load,
    remove_sick_day,
    sick_days,
)
from sickdays._conflict import (
    FreePredicate,
    ensure_not_free,
    ensure_not_sick,
    free_day_predicate,
)
from sickdays._constants import (
    LOCKER_ALARM,
    LOCKER_BOOK,
    LOCKER_DIET,
    LOCKER_LEETCODE,
    LOCKER_WORKOUT,
    LOCKERS,
)
from sickdays._day import parse_iso, resolve, to_iso, today
from sickdays._errors import (
    AlreadySickError,
    ConflictCheckUnavailableError,
    FreeDayConflictError,
    NotSickError,
    PastDateError,
    SickDayConflictError,
    SickDayError,
    UnreadablePoolError,
)
from sickdays._keep_api import kept_lockers, set_kept_lockers, stands_down
from sickdays._model import SickDay
from sickdays._paths import Paths
from sickdays._sync import SyncUnavailableError, sync, sync_quietly

__all__ = [
    "LOCKERS",
    "LOCKER_ALARM",
    "LOCKER_BOOK",
    "LOCKER_DIET",
    "LOCKER_LEETCODE",
    "LOCKER_WORKOUT",
    "AlreadySickError",
    "ConflictCheckUnavailableError",
    "FreeDayConflictError",
    "FreePredicate",
    "NotSickError",
    "PastDateError",
    "Paths",
    "SickDay",
    "SickDayConflictError",
    "SickDayError",
    "SyncUnavailableError",
    "UnreadablePoolError",
    "actor_id",
    "add_sick_day",
    "ensure_not_free",
    "ensure_not_sick",
    "free_day_predicate",
    "import_legacy",
    "is_sick_day",
    "kept_lockers",
    "load",
    "parse_iso",
    "remove_sick_day",
    "resolve",
    "set_kept_lockers",
    "sick_days",
    "stands_down",
    "sync",
    "sync_quietly",
    "to_iso",
    "today",
]
