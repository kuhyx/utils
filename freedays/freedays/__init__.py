# Copyright (c) 2026 Krzysztof Rudnicki
"""One shared pool of pre-declared days on which every gate app stands down.

The whole point of this package fits in one call. A gate app asks::

    import freedays

    if freedays.is_free_day():
        return  # no lock, no dialog, no alarm -- say nothing

That is the entire integration. It reads one local file, never the network,
and answers ``False`` for anything it cannot parse, so the failure mode is
"the normal rules apply", never "everything is switched off".

Two properties are deliberate and load-bearing:

* **Nothing here ever initiates.** No notification, no warning when the pool
  runs low, no prompt when a gate fires. The pool is consulted silently and
  reported only when someone runs ``freedays status``.
* **One global pool.** A free day is free for every app at once. There is no
  per-app dimension to mark, and none to forget to mark.

Free days are *not* sick days. Sick days stay where they are, with their
rolling windows and their justification friction, because they exist to be
hard to take. These exist to be easy: declared in advance, no reason
required, consecutive runs allowed, capped only by an annual budget.
"""

from __future__ import annotations

from freedays._api import (
    Status,
    actor_id,
    is_free_day,
    load,
    lookup,
    mark,
    release,
    save,
    status,
)
from freedays._budget import free_days_in_year, is_exhausted, remaining, spent
from freedays._constants import DEFAULT_ANNUAL_BUDGET
from freedays._day import parse_iso, resolve, to_iso, today
from freedays._errors import (
    AlreadyFreeError,
    BudgetExhaustedError,
    FreeDayError,
    NotFreeError,
    PastDateError,
)
from freedays._model import FreeDay
from freedays._paths import Paths
from freedays._sync import SyncUnavailableError, sync, sync_quietly

__all__ = [
    "DEFAULT_ANNUAL_BUDGET",
    "AlreadyFreeError",
    "BudgetExhaustedError",
    "FreeDay",
    "FreeDayError",
    "NotFreeError",
    "PastDateError",
    "Paths",
    "Status",
    "SyncUnavailableError",
    "actor_id",
    "free_days_in_year",
    "is_exhausted",
    "is_free_day",
    "load",
    "lookup",
    "mark",
    "parse_iso",
    "release",
    "remaining",
    "resolve",
    "save",
    "spent",
    "status",
    "sync",
    "sync_quietly",
    "to_iso",
    "today",
]
