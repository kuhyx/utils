# Copyright (c) 2026 Krzysztof Rudnicki
"""A date is never both a free day and a sick day (0.4.0).

Sick days are a separate pool (``sickdays``, its own file and remote node).
sickdays depends on freedays, never the other way round, so this module
imports it *at call time, by name* -- no module-level import, no cycle.

If sickdays is not installed the mark is **allowed** and a warning logged.
freedays is load-bearing on hosts that never get sickdays (the gaming
daemon's root env, CI), and on such a host there is no local sick-day pool
to conflict with; refusing every free day there would be a regression for
nothing. The other direction (a sick day on a free date) is refused by
sickdays itself, which fails closed.
"""

from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING, cast

from freedays._day import to_iso
from freedays._errors import SickDayConflictError

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import date

_logger = logging.getLogger(__name__)


def is_sick_predicate() -> Callable[[date], bool] | None:
    """``sickdays.is_sick_day``, imported now; ``None`` (logged) if absent."""
    try:
        module = importlib.import_module("sickdays")
    except ImportError:
        _logger.warning(
            "sickdays is not installed: cannot check the sick-day pool, "
            "so the free day is marked unchecked"
        )
        return None
    return cast("Callable[[date], bool]", module.is_sick_day)


def refuse_if_sick(day: date) -> None:
    """Refuse to mark ``day`` free when it is a sick day.

    Raises:
        SickDayConflictError: ``day`` is a sick day.
    """
    is_sick = is_sick_predicate()
    if is_sick is not None and is_sick(day):
        msg = (
            f"{to_iso(day)} is a sick day -- remove it with "
            "'sickdays remove' before marking it free"
        )
        raise SickDayConflictError(msg)
