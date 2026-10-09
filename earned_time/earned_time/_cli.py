# Copyright (c) 2026 Krzysztof Rudnicki
"""``python -m earned_time maturity``: every gate's verdict, as a table or JSON.

Claude runs this before answering any "grant me X" request and follows the
verdict: lenient to a ``new`` gate, suspicious for a ``mature`` one.

This is the one place that resolves real paths -- the library never does
(:mod:`earned_time._ledger`). Both are module names so tests redirect them.
It only ever reads a ledger.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
from datetime import UTC, date, datetime
import json
from pathlib import Path
import sys
from typing import TYPE_CHECKING, Final

from earned_time._maturity import Maturity, maturity
from earned_time._registry import all_earners, earners_for

if TYPE_CHECKING:
    from collections.abc import Sequence

    from earned_time._policy import Earner

KEY_FILE: Final = Path("/etc/workout-locker/hmac.key")
# Display only: gates with no earn-back, so nothing here classifies them.
NOT_CLASSIFIED: Final = ("diet-guard", "home-guard", "hosts-blocker", "wake-alarm")

_COLUMNS: Final = (
    "gate",
    "level",
    "days",
    "first",
    "last",
    "confirmed_on",
    "penalty_from",
    "penalty_start",
    "reasons",
)


def home() -> Path:
    """Where ``Earner.ledger`` paths are rooted (the user's home)."""
    return Path.home()


def _gates(day: date) -> list[tuple[str, Earner, Maturity]]:
    """Each ledger-backed earner of every registry, with its verdict on ``day``.

    Two earners can share a name across registries (``automation`` before and
    after ``TUTOR_FROM``); those get their ledger's directory appended.
    """
    earners = [e for e in all_earners() if e.ledger is not None]
    names = Counter(e.name for e in earners)
    registered = earners_for(day)
    gates = []
    for item in earners:
        ledger = Path(str(item.ledger))
        gate = item.name
        if names[item.name] > 1:
            gate = f"{item.name}:{ledger.parent.name}"
        verdict = maturity(item, home() / ledger, KEY_FILE, day)
        if item not in registered:
            extra = f"not in the registry on {day}: neither paid nor penalised"
            verdict = replace(verdict, reasons=(*verdict.reasons, extra))
        gates.append((gate, item, verdict))
    return gates


def _iso(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _record(gate: str, item: Earner, verdict: Maturity) -> dict[str, object]:
    return {
        "gate": gate,
        "name": verdict.name,
        "ledger": item.ledger,
        "level": verdict.level,
        "credit_days": verdict.credit_days,
        "credit_rows": verdict.credit_rows,
        "first_credit": _iso(verdict.first_credit),
        "last_credit": _iso(verdict.last_credit),
        "confirmed_on": _iso(verdict.confirmed_on),
        "penalty_from": _iso(verdict.penalty_from),
        "penalty_start": _iso(verdict.penalty_start),
        "checked": verdict.checked,
        "reasons": list(verdict.reasons),
    }


def _row(gate: str, verdict: Maturity) -> list[str]:
    cells = (
        verdict.level,
        verdict.credit_days,
        verdict.first_credit,
        verdict.last_credit,
        verdict.confirmed_on,
        verdict.penalty_from,
        verdict.penalty_start,
    )
    shown = ["-" if c is None else str(c) for c in cells]
    return [gate, *shown, "; ".join(verdict.reasons)]


def render_table(gates: Sequence[tuple[str, Maturity]]) -> str:
    """The verdicts as a fixed-width table; the reasons column runs free."""
    rows = [list(_COLUMNS), *(_row(gate, verdict) for gate, verdict in gates)]
    widths = [max(len(row[i]) for row in rows) for i in range(len(_COLUMNS) - 1)]
    lines = [
        "  ".join([*(c.ljust(w) for c, w in zip(row, widths, strict=False)), row[-1]])
        for row in rows
    ]
    return "\n".join(line.rstrip() for line in lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m earned_time")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("maturity", help="how far to trust each gate")
    command.add_argument("--json", action="store_true", help="machine-readable")
    command.add_argument(
        "--day", type=date.fromisoformat, help="verdict day (YYYY-MM-DD)"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI; returns the exit status."""
    args = _parser().parse_args(argv)
    day: date = args.day or datetime.now(tz=UTC).astimezone().date()
    gates = _gates(day)
    if args.json:
        records = [_record(*gate) for gate in gates]
        payload = {
            "day": day.isoformat(),
            "gates": records,
            "not_classified": list(NOT_CLASSIFIED),
        }
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return 0
    sys.stdout.write(
        f"gate maturity on {day}\n{render_table([(g, v) for g, _, v in gates])}\n"
    )
    sys.stdout.write(f"not classified (no earn-back): {', '.join(NOT_CLASSIFIED)}\n")
    return 0
