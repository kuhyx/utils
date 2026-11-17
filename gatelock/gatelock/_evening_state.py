# Copyright (c) 2026 Krzysztof Rudnicki
"""What the evening chain reads: constants, sources and today's verdict.

Split from :mod:`gatelock.evening_chain` (the CLI and the run loop) to keep
each file readable in one piece. Import the public names from there.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol

import earned_time
import freedays
import sickdays

from gatelock.log_integrity import DEFAULT_HMAC_KEY_FILE

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date, datetime


class _Earner(Protocol):
    """What this module reads off an ``earned_time.Earner``."""

    ledger: str
    max_units: int | None


_logger: Final = logging.getLogger(__name__)

EXIT_OK: Final = 0
EXIT_NOTHING: Final = 1
EXIT_UNCHECKABLE: Final = 2
EXIT_NO_X: Final = 3
EXIT_END_EVENING: Final = 10
"""A gate's "end evening" control: stop the chain, lockdown at the next tick."""

CHAIN: Final = ("reading", "tutor", "leetcode")
CUTOFF: Final = time(23, 0)
"""The only hard time: from here no gate runs and nothing is pending."""
MAX_FAILURES_IN_A_ROW: Final = 2

_PYTHON: Final = "/usr/bin/python3"
GATE_COMMANDS: Final[Mapping[str, tuple[str, ...]]] = {
    "reading": (_PYTHON, "-m", "book_guard", "lock", "--production", "--evening"),
    "tutor": (_PYTHON, "-m", "tutor.gate", "--production", "--evening"),
    "leetcode": (_PYTHON, "-m", "leetcode_guard", "--production", "--evening"),
}
TUTOR: Final = "tutor"
LEETCODE: Final = "leetcode"

# What a ledger read may raise; anything else is a bug and surfaces in main().
_CHECK_ERRORS: Final = (OSError, ValueError, TypeError, LookupError, RuntimeError)


@dataclass(frozen=True)
class Sources:
    """Every file the chain reads. No defaults: callers say where."""

    home: Path
    key_file: Path
    free_log: Path | None  # None: freedays' own pool
    sick_log: Path | None  # None: sickdays' own pool


@dataclass(frozen=True)
class Verdict:
    """Today's chain: the rungs still to run, in order, and why none."""

    todo: tuple[str, ...] = ()
    unchecked: tuple[str, ...] = ()
    stood_down: str = ""  # "free", "sick", "late" or ""


def production_sources() -> Sources:
    """The real machine's files: ``$HOME`` ledgers, the shared HMAC key."""
    return Sources(Path.home(), Path(DEFAULT_HMAC_KEY_FILE), None, None)


def _charged_today(ledger: Path, sources: Sources, day: date) -> bool:
    """Whether a verified ``charge`` row names ``day``, whatever its source.

    A day settled by the escape hatch or a LeetCode outage carries a
    non-paying charge, and the gate then writes no ``source=leetcode`` row, so
    the rung can never be paid. earned_time has no public helper for "any
    charge" (``done_today`` only sees the paying one), so this reads the rows
    itself and trusts only signed ones. Raises OSError/ValueError when the
    ledger or key cannot be read.
    """
    key = sources.key_file.read_bytes().strip()
    rows = json.loads(ledger.read_text(encoding="utf-8"))["entries"]
    return any(
        isinstance(row, dict)
        and row.get("kind") == "charge"
        and row.get("day") == day.isoformat()
        and earned_time.verified(row, key)
        for row in rows
    )


def _paid(rung: str, earner: _Earner, sources: Sources, now: datetime) -> bool | None:
    """Whether ``rung`` has nothing to run; None when it could not be checked.

    The LeetCode rung also counts as settled on a day an unpaying charge
    closed (see :func:`_charged_today`): it is not payable, so not pending.
    """
    ledger = sources.home / earner.ledger
    try:
        if rung == TUTOR:
            units = earned_time.credit_units(
                earner, ledger, sources.key_file, now.date()
            )
            cap = earner.max_units
            return None if units is None or cap is None else units >= cap
        done = earned_time.done_today(
            earner, ledger, sources.key_file, now=now, gate_off=False
        )
        if done is None:
            return None
        if done or rung != LEETCODE:
            return bool(done)
        return _charged_today(ledger, sources, now.date())
    except _CHECK_ERRORS:
        _logger.exception("Could not check the %s rung", rung)
        return None


def evaluate(now: datetime, sources: Sources) -> Verdict:
    """Which rungs are unpaid at ``now``; free/sick/late days stand down."""
    now = now.astimezone()
    if now.time() >= CUTOFF:
        return Verdict(stood_down="late")
    day = now.date()
    if freedays.is_free_day(day, log_path=sources.free_log):
        return Verdict(stood_down="free")
    if sickdays.is_sick_day(day, log_path=sources.sick_log):
        return Verdict(stood_down="sick")
    earners = {e.name: e for e in earned_time.earners_for(day)}
    todo: list[str] = []
    unchecked: list[str] = []
    for rung in CHAIN:
        if rung not in earners:
            continue
        paid = _paid(rung, earners[rung], sources, now)
        if paid is None:
            unchecked.append(rung)
        if not paid:
            todo.append(rung)
    return Verdict(tuple(todo), tuple(unchecked))
