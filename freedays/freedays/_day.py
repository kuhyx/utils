# Copyright (c) 2026 Krzysztof Rudnicki
"""What "today" means, in one place.

The apps this package serves disagreed about this before it existed:
screen-locker's lock chain computed the day in UTC while the tool that wrote
its skip file computed it in *local* time, so a skip added near midnight
could name a date the chain never matched. Free days are a human-facing
calendar concept -- if it is Tuesday where the person is standing, it is
Tuesday -- so this package is local-time throughout and nothing else is
allowed a second opinion.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

ISO_FORMAT = "%Y-%m-%d"


def today(now: date | None = None) -> date:
    """Return the current local calendar date.

    Args:
        now: Override for tests and for callers that already resolved a
            reference date. ``None`` reads the system clock in local time.

    Returns:
        The local calendar date.
    """
    return now if now is not None else datetime.now(tz=UTC).astimezone().date()


def parse_iso(text: str) -> date:
    """Parse ``YYYY-MM-DD`` into a :class:`~datetime.date`.

    Args:
        text: The date string.

    Returns:
        The parsed date.

    Raises:
        ValueError: If ``text`` is not a valid ``YYYY-MM-DD`` date. The
            message names the offending input, because the usual way to see
            this is a typo on the command line.
    """
    try:
        return date.fromisoformat(text.strip())
    except ValueError as exc:
        msg = f"not a YYYY-MM-DD date: {text!r}"
        raise ValueError(msg) from exc


def to_iso(day: date) -> str:
    """Render ``day`` as ``YYYY-MM-DD``."""
    return day.strftime(ISO_FORMAT)


def resolve(text: str, *, now: date | None = None) -> date:
    """Parse a user-supplied day, accepting ``today`` and ``tomorrow``.

    Args:
        text: A ``YYYY-MM-DD`` date, or the words ``today``/``tomorrow``.
        now: Reference date for the relative words.

    Returns:
        The resolved date.

    Raises:
        ValueError: If ``text`` is neither a keyword nor a valid date.
    """
    cleaned = text.strip().lower()
    reference = today(now)
    if cleaned == "today":
        return reference
    if cleaned == "tomorrow":
        return reference + timedelta(days=1)
    return parse_iso(text)
