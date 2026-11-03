# Copyright (c) 2026 Krzysztof Rudnicki
"""Public API: query (fails closed) and mutate (ratchet-checked) holds."""

from __future__ import annotations

from datetime import datetime
import logging

from holds import _store
from holds._model import Hold, HoldsError, naive
from holds._rules import make_id, validate

_LOG = logging.getLogger("holds")


def _now(now: datetime | None) -> datetime:
    return naive(now) if now is not None else datetime.now()


def _safe_load() -> list[Hold]:
    """Fail CLOSED: an untrustworthy file means no hold (gates act normally)."""
    try:
        return _store.load()
    except HoldsError:
        _LOG.exception("ignoring hold file; gates behave as normal")
        return []


def active(now: datetime | None = None) -> Hold | None:
    """The hold covering ``now`` (earliest start if hand-edits overlap), or None."""
    moment = _now(now)
    hits = [h for h in _safe_load() if h.contains(moment)]
    return min(hits, key=lambda h: h.start) if hits else None


def covers(gate: str, now: datetime | None = None) -> bool:
    """Whether ``gate`` stands down at ``now``. v1: every gate does."""
    del gate  # kept for future per-gate holds
    return active(now) is not None


def next_change(now: datetime | None = None) -> datetime | None:
    """When the active hold ends, else when the next one starts, else None."""
    moment = _now(now)
    current = active(moment)
    if current is not None:
        return current.end
    upcoming = [h.start for h in _safe_load() if h.start > moment]
    return min(upcoming) if upcoming else None


def add(
    start: datetime, end: datetime, reason: str, now: datetime | None = None
) -> Hold:
    """Declare a hold. Raises HoldsError on any ratchet violation."""
    moment = _now(now)
    begin, finish = naive(start), naive(end)
    existing = _store.load()
    clean = validate(existing, begin, finish, reason, moment)
    hold = Hold(make_id(existing, begin, clean), begin, finish, clean, moment)
    _store.save([*existing, hold])
    return hold


def remove(hold_id: str, now: datetime | None = None) -> None:
    """Delete a hold that has not started yet."""
    moment = _now(now)
    existing = _store.load()
    target = next((h for h in existing if h.id == hold_id), None)
    if target is None:
        msg = f"unknown hold: {hold_id}"
        raise HoldsError(msg)
    if target.start <= moment:
        msg = "hold already started; it cannot be removed"
        raise HoldsError(msg)
    _store.save([h for h in existing if h.id != hold_id])
