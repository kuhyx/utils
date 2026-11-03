# Copyright (c) 2026 Krzysztof Rudnicki
"""Ratchet rules for new holds (R11): only ever stricter, never an escape hatch."""

from __future__ import annotations

from datetime import datetime, timedelta
import re

from holds._model import Hold, HoldsError

MAX_DURATION = timedelta(hours=15)
MAX_PER_WEEK = 3
MIN_LEAD = timedelta(minutes=30)
MIN_REASON = 10


def _week(moment: datetime) -> tuple[int, int]:
    iso = moment.isocalendar()
    return iso.year, iso.week


def validate(
    existing: list[Hold], start: datetime, end: datetime, reason: str, now: datetime
) -> str:
    """Raise HoldsError on any violation; return the stripped reason."""
    if start.second or start.microsecond or end.second or end.microsecond:
        msg = "start and end must be whole minutes"
        raise HoldsError(msg)
    if end <= start:
        msg = "end must be after start"
        raise HoldsError(msg)
    if end - start > MAX_DURATION:
        msg = "a hold may last at most 15 h"
        raise HoldsError(msg)
    if start < now + MIN_LEAD:
        msg = "a hold must start at least 30 min from now"
        raise HoldsError(msg)
    clean = reason.strip()
    if len(clean) < MIN_REASON:
        msg = f"reason must be at least {MIN_REASON} chars"
        raise HoldsError(msg)
    if any(h.start < end and start < h.end for h in existing):
        msg = "hold would overlap an existing hold"
        raise HoldsError(msg)
    if sum(_week(h.start) == _week(start) for h in existing) >= MAX_PER_WEEK:
        msg = f"at most {MAX_PER_WEEK} holds per ISO week"
        raise HoldsError(msg)
    return clean


def make_id(existing: list[Hold], start: datetime, reason: str) -> str:
    """``YYYYMMDDTHHMM-<slug>``; unique because holds never overlap."""
    slug = re.sub(r"[^a-z0-9]+", "-", reason.lower()).strip("-")[:40].strip("-")
    base = f"{start:%Y%m%dT%H%M}-{slug or 'hold'}"
    taken = {h.id for h in existing}
    candidate, n = base, 2
    while candidate in taken:
        candidate = f"{base}-{n}"
        n += 1
    return candidate
