# Copyright (c) 2026 Krzysztof Rudnicki
"""The evening gate chain: book, then tutor, then LeetCode, before lockdown.

When the resolved shutdown time arrives and a rung of the chain is unpaid
today, root (digital-wellbeing's day-specific-shutdown-check) asks this module
instead of entering night lockdown:

* ``python3 -m gatelock.evening_chain pending`` -- prints the unpaid rungs.
  Exit 0 some rung is unpaid; 1 nothing to do (all paid, a free or sick day,
  or 23:00 or later); 2 could not check. Root calls it every minute, so it
  reads three small files and nothing else.
* ``python3 -m gatelock.evening_chain run`` -- the ``evening-gates.service``
  body: each unpaid rung's gate in order, until all are paid.

"Paid today" is read-only from the signed ledgers (``earned_time``): reading
and LeetCode by ``done_today``, the tutor by QUOTA (``credit_units`` reaching
``max_units``). A rung not in ``earned_time.earners_for(day)`` is not asked.

Failure modes, chosen out loud. ``pending`` fails CLOSED: an unreadable
ledger or key, a missing dependency or any exception is exit 2 on stderr, and
root then enters lockdown. ``run`` treats a rung it cannot check as unpaid
(its gate stays up and decides itself) but never spins: a gate that fails,
or exits 0 with the rung still unpaid, is skipped for the evening, and two
such failures in a row stop the chain with exit 1.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import logging
import subprocess
import sys
from typing import TYPE_CHECKING, Final

from gatelock._evening_state import (
    CHAIN,
    CUTOFF,
    EXIT_END_EVENING,
    EXIT_NO_X,
    EXIT_NOTHING,
    EXIT_OK,
    EXIT_UNCHECKABLE,
    GATE_COMMANDS,
    MAX_FAILURES_IN_A_ROW,
    Sources,
    Verdict,
    evaluate,
    production_sources,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

__all__ = [
    "CHAIN",
    "CUTOFF",
    "EXIT_END_EVENING",
    "EXIT_NO_X",
    "GATE_COMMANDS",
    "Sources",
    "Verdict",
    "evaluate",
    "main",
    "pending",
    "run",
]

_logger: Final = logging.getLogger(__name__)

# Everything a broken install or ledger can plausibly raise. A tuple, not a
# bare ``except Exception``: pylint bans that and per-line suppressions are
# banned here. Anything outside it is a traceback and exit 1, which root also
# reads as "enter lockdown" (fail closed either way).
_ANY_FAILURE: Final = (
    OSError,
    ValueError,
    TypeError,
    LookupError,
    RuntimeError,
    ImportError,
    AttributeError,
    ArithmeticError,
    AssertionError,
    NameError,
)

type Clock = Callable[[], datetime]
type Runner = Callable[[Sequence[str], float], int | None]
"""Runs one gate command with a timeout in seconds; None means it timed out."""


def pending(sources: Sources, clock: Clock, emit: Callable[[str], None]) -> int:
    """``pending``'s answer: print the unpaid rungs, return its exit code."""
    verdict = evaluate(clock(), sources)
    if verdict.stood_down:
        _logger.info("Evening chain stands down: %s", verdict.stood_down)
        return EXIT_NOTHING
    if verdict.unchecked:
        _logger.error("Could not check: %s", " ".join(verdict.unchecked))
        return EXIT_UNCHECKABLE
    if not verdict.todo:
        return EXIT_NOTHING
    emit(" ".join(verdict.todo))
    return EXIT_OK


def subprocess_runner(cmd: Sequence[str], timeout_s: float) -> int | None:
    """Run a gate; on timeout kill it and return None."""
    try:
        return subprocess.run(cmd, check=False, timeout=timeout_s).returncode
    except subprocess.TimeoutExpired:
        return None
    except OSError:
        _logger.exception("Cannot start %s", cmd[0])
        return 127


def _seconds_to_cutoff(now: datetime) -> float:
    cutoff = datetime.combine(now.date(), CUTOFF, now.tzinfo)
    return max((cutoff - now).total_seconds(), 1.0)


def _stop_code(rung: str, code: int | None) -> int | None:
    """The run's own exit code when ``code`` ends the chain, else None."""
    if code is None:
        _logger.warning("%s gate still up at %s; stopping", rung, CUTOFF)
        return EXIT_OK
    return {EXIT_END_EVENING: EXIT_OK, EXIT_NO_X: EXIT_NO_X}.get(code)


def run(sources: Sources, clock: Clock, runner: Runner) -> int:
    """Run each unpaid rung's gate in order; see the module docstring."""
    skipped: list[str] = []
    ran_clean = ""  # a rung whose gate exited 0 and must now read as paid
    failures = 0
    while True:
        now = clock().astimezone()
        verdict = evaluate(now, sources)
        if ran_clean in verdict.todo:
            _logger.error("%s gate exited 0 but the rung is unpaid", ran_clean)
            skipped.append(ran_clean)
            failures += 1
        elif ran_clean:
            failures = 0
        ran_clean = ""
        if failures >= MAX_FAILURES_IN_A_ROW:
            _logger.error("Two gates failed in a row; stopping the chain")
            return EXIT_NOTHING
        if verdict.stood_down:
            return EXIT_OK
        todo = [r for r in verdict.todo if r not in skipped]
        if not todo:
            return EXIT_NOTHING if verdict.todo else EXIT_OK
        rung = todo[0]
        code = runner(GATE_COMMANDS[rung], _seconds_to_cutoff(now))
        stop = _stop_code(rung, code)
        if stop is not None:
            return stop
        if code == 0:
            ran_clean = rung
            continue
        _logger.error("%s gate failed with exit %d; skipping it", rung, code)
        skipped.append(rung)
        failures += 1


def main(
    argv: Sequence[str] | None = None,
    *,
    sources: Sources | None = None,
    clock: Clock | None = None,
    runner: Runner | None = None,
) -> int:
    """CLI entry. Collaborators are injectable; defaults are production."""
    parser = argparse.ArgumentParser(prog="python3 -m gatelock.evening_chain")
    parser.add_argument("command", choices=("pending", "run"))
    command = parser.parse_args(argv).command
    handler = logging.StreamHandler(sys.stderr)
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        where = sources if sources is not None else production_sources()
        now = clock if clock is not None else (lambda: datetime.now(tz=UTC))
        if command == "pending":
            return pending(where, now, print)
        return run(where, now, runner if runner is not None else subprocess_runner)
    except _ANY_FAILURE:
        _logger.exception("Evening chain %s failed", command)
        return EXIT_UNCHECKABLE if command == "pending" else EXIT_NOTHING
    finally:
        root.removeHandler(handler)


if __name__ == "__main__":
    sys.exit(main())
