# Copyright (c) 2026 Krzysztof Rudnicki
"""The leisure budget: from ``leisure_from()`` gaming time covers all leisure.

The daily "gaming" budget becomes a budget for every non-productive activity
on the PC (games, browsing, video, messaging), so a fully earned day grows
from 8 h to 10 h: the base rises 5 h -> 7 h and the cap 8 h -> 10 h. Earner
pay, penalties and the shutdown ladder are untouched, so a day still earns
exactly what it did; only the floor and the cap move, by the same 2 h.

The first leisure day is the switch file ``LEISURE_FROM_PATH`` (0.15.0),
written by ``leisure-watch go-live`` (always tomorrow's date); without a
readable one it is the parked ``LEISURE_FROM``. Earlier days keep
``GAMING_BASE_MINUTES`` and ``GAMING_CEILING_MINUTES``, byte-identical.
``resolve(..., leisure=True)`` prices any day with the leisure base and cap:
the shadow budget the enforcer reports while it still enforces the old one.
"""

from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import re
import stat
from typing import Final

from earned_time._policy import GAMING_BASE_MINUTES, GAMING_CEILING_MINUTES

# Parked far ahead: the switch file moves it, never a same-day cut (2026-09-26).
LEISURE_FROM: Final = date(2027, 1, 1)
# One line ``YYYY-MM-DD``, root:root 0644 (contract C6 of the leisure rollout).
LEISURE_FROM_PATH: Final = Path("/etc/leisure-watch/leisure_from")
# From the first leisure day: 7 h base, 10 h cap (+2 h each).
LEISURE_BASE_MINUTES: Final = 7 * 60
LEISURE_CEILING_MINUTES: Final = 10 * 60

_MAX_BYTES: Final = 64
# Checked before fromisoformat, which also takes "20261020" and "2026-W43-2".
_ISO_DAY: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\n?")
# NONBLOCK: a FIFO planted there must not hang the root daemon on open().
_OPEN_FLAGS: Final = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC


def _read_day(path: Path) -> date | None:
    """The date in ``path`` if it is a small regular file holding one; else None."""
    fd = os.open(path, _OPEN_FLAGS)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        raw = os.read(fd, _MAX_BYTES + 1)
    finally:
        os.close(fd)
    text = raw.decode("ascii")
    if len(raw) > _MAX_BYTES or not _ISO_DAY.fullmatch(text):
        return None
    return date.fromisoformat(text.rstrip("\n"))


def leisure_from(path: Path = LEISURE_FROM_PATH) -> date:
    """The first leisure day: the switch file's date, else ``LEISURE_FROM``.

    Read afresh on every call (go-live can write it mid-run), never following
    a symlink or blocking on a FIFO. Anything but a regular file of at most
    64 bytes holding exactly ``YYYY-MM-DD`` (one optional newline) -- missing,
    unreadable, garbage, an impossible date -- is the parked ``LEISURE_FROM``.
    Never raises.
    """
    try:
        day = _read_day(path)
    except OSError, ValueError:  # UnicodeDecodeError is a ValueError
        return LEISURE_FROM
    return LEISURE_FROM if day is None else day


def leisure_active(day: date, path: Path = LEISURE_FROM_PATH) -> bool:
    """Is ``day`` (a gaming day) on the leisure budget? ``day >= leisure_from()``.

    The only way a consumer may ask "is Phase 2 on?"; none reads the file.
    """
    return day >= leisure_from(path)


def is_leisure(day: date, *, leisure: bool = False) -> bool:
    """``leisure`` (forced: the shadow budget) or ``day`` is a leisure day.

    Looks ``LEISURE_FROM_PATH`` up at call time, so tests can redirect it.
    """
    return leisure or leisure_active(day, LEISURE_FROM_PATH)


def base_minutes(*, leisure: bool) -> int:
    """The gaming base before penalties: 7 h on the leisure budget, else 5 h."""
    return LEISURE_BASE_MINUTES if leisure else GAMING_BASE_MINUTES


def ceiling_minutes(*, leisure: bool) -> int:
    """The gaming cap: 10 h on the leisure budget, else 8 h."""
    return LEISURE_CEILING_MINUTES if leisure else GAMING_CEILING_MINUTES


def gaming_base_minutes_for(day: date) -> int:
    """The gaming base before penalties: 7 h from ``leisure_from()``, else 5 h."""
    return base_minutes(leisure=is_leisure(day))


def gaming_ceiling_minutes_for(day: date) -> int:
    """The gaming cap: 10 h from ``leisure_from()``, else 8 h."""
    return ceiling_minutes(leisure=is_leisure(day))
