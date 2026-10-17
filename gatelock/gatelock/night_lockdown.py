# Copyright (c) 2026 Krzysztof Rudnicki
"""Has tonight's evening night-lockdown already happened?

night-lockdown (digital-wellbeing, ``night-lockdown-enter.sh``) stamps
``/var/lib/night-lockdown/locked_at_epoch`` with a unix epoch every time it
locks, and never removes it. Earner gates (workout, LeetCode, reading) that
opt in call :func:`evening_lockdown_today` and do not re-arm their lock for
the rest of a day whose evening lockdown already fired: once a late credit
lifted that lockdown, re-locking behind a task gate the same evening would
make the finished task impossible to submit.

Only an EVENING lock counts -- the stamp's local date is today and its local
time is at or after 12:00. The 04:01 re-lock of the morning window is the
night that began yesterday, not tonight's.

Fail open to "no lockdown" (the gate locks as before): a missing stamp is the
normal state on a fresh machine and stays quiet; an unreadable or garbage
stamp is a warning, because then the signal itself is broken.

Opt-in by design: a gate that is not an earner (diet-guard) never calls this.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
import logging
from pathlib import Path
from typing import Final

_logger = logging.getLogger(__name__)

NIGHT_LOCKDOWN_STAMP: Final = Path("/var/lib/night-lockdown/locked_at_epoch")
"""Where night-lockdown-enter.sh writes the epoch of its latest lock."""

EVENING_FROM: Final = time(12, 0)
"""A same-day lock at or after this local time is the evening lockdown."""


def _read_stamp(path: Path) -> datetime | None:
    """The stamp as a local instant, or None when absent or unusable."""
    try:
        text = path.read_text(encoding="ascii")
    except FileNotFoundError:
        _logger.debug("No night-lockdown stamp at %s", path)
        return None
    except (OSError, UnicodeDecodeError) as exc:
        _logger.warning(
            "Cannot read night-lockdown stamp %s (%s); treating as no lockdown",
            path,
            exc,
        )
        return None
    try:
        return datetime.fromtimestamp(int(text.strip()), tz=UTC).astimezone()
    except (ValueError, OverflowError, OSError) as exc:
        _logger.warning(
            "Night-lockdown stamp %s is not a unix epoch (%r: %s); "
            "treating as no lockdown",
            path,
            text[:40],
            exc,
        )
        return None


def evening_lockdown_today(
    path: Path = NIGHT_LOCKDOWN_STAMP,
    now: datetime | None = None,
) -> datetime | None:
    """When today's evening lockdown locked, or None if it has not yet.

    Truthy exactly when the stamp's local date is ``now``'s and its local
    time is at or after :data:`EVENING_FROM` (and not in the future), so it
    reads as a predicate while still giving callers the time to quote.
    """
    now = (now or datetime.now(tz=UTC)).astimezone()
    locked_at = _read_stamp(path)
    if locked_at is None:
        return None
    if locked_at.date() != now.date() or locked_at.time() < EVENING_FROM:
        return None
    if locked_at > now:
        _logger.warning(
            "Night-lockdown stamp %s is in the future (%s > %s); ignoring it",
            path,
            locked_at.isoformat(),
            now.isoformat(),
        )
        return None
    return locked_at
