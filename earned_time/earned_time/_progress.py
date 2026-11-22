# Copyright (c) 2026 Krzysztof Rudnicki
"""The signed progress fact (0.24.0): "done N of target M for day D".

earned_time cannot derive a gate's plan, so each gate signs the fact in its own
ledger and this module only reads it (DOCS-progress.md). The row::

    {"kind": "progress", "entry_id": "progress:<day>:<done>:<target>",
     "day": "<day>", "amount": 0, "device": ..., "created_at": ...,
     "detail": {"source": <progress source>, "for_day": "YYYY-MM-DD",
                "done": "<digits>", "target": "<digits>"}, "hmac": ...}

**Fail closed.** Everything but a verified, well-formed, same-day row is
``None``, and ``None`` means "pays by today's yes/no rule", never more.
Unreadable inputs are logged at warning; nothing here raises.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from earned_time._ledger import read_key, read_rows, verified
from earned_time._registry import earners_for

if TYPE_CHECKING:
    from collections.abc import Container
    from datetime import date
    from pathlib import Path

    from earned_time._policy import Earner

_KIND: Final = "progress"
# Digits a count may have: far beyond any real plan, below int()'s own limit.
_MAX_DIGITS: Final = 9


@dataclass(frozen=True)
class Progress:
    """``done`` units of a ``target``-unit plan, as the gate signed it."""

    done: int
    target: int


def _count(raw: object) -> int | None:
    """A count from ASCII digits only (never an int, float, sign or space)."""
    if not (isinstance(raw, str) and raw.isascii() and raw.isdigit()):
        return None
    return int(raw) if len(raw) <= _MAX_DIGITS else None


def _fact(row: dict[str, object], source: str, day: date) -> Progress | None:
    """One row's fact, if it is for ``source`` and ``day`` and well formed."""
    if row.get("kind") != _KIND:
        return None
    detail = row.get("detail")
    if not isinstance(detail, dict):
        return None
    if detail.get("source") != source or detail.get("for_day") != day.isoformat():
        return None
    done, target = _count(detail.get("done")), _count(detail.get("target"))
    if done is None or not target:
        return None
    return Progress(min(done, target), target)


def read_progress(
    earner: Earner,
    ledger: Path,
    key_file: Path,
    day: date,
    *,
    gate_off: bool = False,
) -> Progress | None:
    """``earner``'s signed progress for ``day``, or ``None``.

    Over the rows that verify and match, the largest ``done`` and the largest
    ``target`` (a replay or a lost row can only lower the share, never raise
    it at one target). ``None`` for: no such row, a bad signature, another day
    or source, bad integers, a zero target, an unreadable ledger or key
    (logged), ``gate_off`` (the gate has no price today), or an earner with no
    ``progress_source``.
    """
    source = earner.progress_source
    if gate_off or source is None:
        return None
    key = read_key(key_file)
    rows = None if key is None else read_rows(ledger, earner)
    if key is None or rows is None:
        return None
    facts = [
        f
        for r in rows
        if isinstance(r, dict) and (f := _fact(r, source, day)) and verified(r, key)
    ]
    if not facts:
        return None
    return Progress(max(f.done for f in facts), max(f.target for f in facts))


def progress_map(
    day: date,
    home: Path,
    key_file: Path,
    *,
    earners: tuple[Earner, ...] | None = None,
    gate_off: Container[str] = frozenset(),
) -> dict[str, Progress]:
    """Every registered earner's progress on ``day``, for ``resolve(progress=)``.

    Args:
        day: The day; also picks the registry (:func:`earners_for`).
        home: The home the earners' ``ledger`` paths are relative to.
        key_file: The shared HMAC key.
        earners: A registry to read instead of ``earners_for(day)``.
        gate_off: Names of the earners whose gate is off today, as the consumer
            passes ``gate_off`` to ``done_today`` (they get no progress).

    Returns:
        ``{earner name: Progress}``, only for earners with a fact: empty means
        every term pays by its yes/no answer, exactly as in 0.23.0.
    """
    found: dict[str, Progress] = {}
    for item in earners_for(day) if earners is None else earners:
        if item.ledger is None:
            continue
        fact = read_progress(
            item,
            home / item.ledger,
            key_file,
            day,
            gate_off=item.name in gate_off,
        )
        if fact is not None:
            found[item.name] = fact
    return found
