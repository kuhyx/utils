# Copyright (c) 2026 Krzysztof Rudnicki
"""The one rule shared with freedays: a date is never in both pools.

The design is one-way on purpose. freedays never imports sickdays, and
sickdays never imports freedays at module level -- so neither package can
form an import cycle, and ``import sickdays`` costs nothing extra in a gate.
Instead:

* **Adding a sick day** asks a predicate ``is_free(day) -> bool``.
  :func:`sickdays.add_sick_day` uses :func:`free_day_predicate` by default,
  which imports ``freedays`` *lazily*, at call time, by name. A phone port or
  a test passes its own predicate.
* **Marking a free day** is freedays' write, so its callers (CLIs, the phone,
  the lock screen) call :func:`ensure_not_sick` first. That needs no import
  of freedays at all.

If freedays cannot be imported, the add is *refused*
(:class:`ConflictCheckUnavailableError`): the invariant is hard, and "could
not check" must not pass as "not free".
"""

from __future__ import annotations

from collections.abc import Callable
import importlib
from typing import TYPE_CHECKING, cast

from sickdays._day import to_iso
from sickdays._errors import (
    ConflictCheckUnavailableError,
    FreeDayConflictError,
    SickDayConflictError,
)
from sickdays._model import is_sick_record
from sickdays._paths import resolve_paths
from sickdays._store import read_pool

if TYPE_CHECKING:
    from datetime import date

    from sickdays._paths import Paths

#: "Is this date a free day?" -- freedays' ``is_free_day`` or a stand-in.
FreePredicate = Callable[["date"], bool]


def free_day_predicate() -> FreePredicate:
    """Return ``freedays.is_free_day``, imported now rather than at load time.

    Raises:
        ConflictCheckUnavailableError: freedays is not importable here.
    """
    try:
        module = importlib.import_module("freedays")
    except ImportError as exc:
        msg = (
            "cannot check the free-day pool (freedays is not installed), "
            "so the sick day was not added"
        )
        raise ConflictCheckUnavailableError(msg) from exc
    return cast("FreePredicate", module.is_free_day)


def ensure_not_free(day: date, is_free: FreePredicate) -> None:
    """Refuse a sick day on a date the free-day pool already holds.

    Raises:
        FreeDayConflictError: ``day`` is a free day.
    """
    if is_free(day):
        msg = (
            f"{to_iso(day)} is a free day -- release it with "
            "'freedays release' before marking it sick"
        )
        raise FreeDayConflictError(msg)


def ensure_not_sick(day: date, *, paths: Paths | None = None) -> None:
    """Refuse a free day on a date the sick-day pool already holds.

    For freedays' callers, before ``freedays.mark``. Reads the local pool
    only; an unreadable pool reads as "not sick", like every other reader.

    Raises:
        SickDayConflictError: ``day`` is a sick day.
    """
    record = read_pool(resolve_paths(paths).log).get(to_iso(day))
    if record is not None and is_sick_record(record):
        msg = (
            f"{to_iso(day)} is a sick day -- remove it with "
            "'sickdays remove' before marking it free"
        )
        raise SickDayConflictError(msg)
