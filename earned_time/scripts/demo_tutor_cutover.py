# Copyright (c) 2026 Krzysztof Rudnicki
"""Demo: what the tutor cutover pays, read from a signed temp ledger.

Writes tutor block rows in the exact contract the Automation tutor writes,
signs them with a throwaway key, counts them with the shared reader
(``credit_units``) and resolves the day. Prints gaming minutes and shutdown
for the day before ``TUTOR_FROM`` and for ``TUTOR_FROM`` itself with 0-5
blocks and a tampered row. Touches no real ledger, key or schedule.

Run: ``PYTHONPATH=earned_time python3 earned_time/scripts/demo_tutor_cutover.py``
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import sys
import tempfile

import earned_time
from earned_time import AUTOMATION_TUTOR, TUTOR_FROM, credit_units, entry_signature

_KEY = b"demo-key-not-the-real-one"
_OTHERS = {"workout": 1, "leetcode": 1, "reading": 1}
_NONE = {"workout": 0, "leetcode": 0, "reading": 0}


def _say(line: str) -> None:
    sys.stdout.write(line + "\n")


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _block(session: str, number: int, day: date) -> dict[str, object]:
    start = datetime.combine(day, time(18)).astimezone()
    ended = (start + timedelta(minutes=15 * number)).timestamp()
    row: dict[str, object] = {
        "kind": "credit",
        "entry_id": f"{session}-b{number}",
        "day": day.isoformat(),
        "created_at": ended + 1,
        "detail": {
            "session_id": session,
            "block": number,
            "active_seconds": 900,
            "ended_at": ended,
            "checks_passed": 3,
            "checks_total": 3,
        },
    }
    return {**row, "hmac": entry_signature(row, _KEY)}


def _units(folder: Path, rows: list[dict[str, object]], day: date) -> int:
    ledger = folder / "ledger.json"
    ledger.write_text(json.dumps({"entries": rows}), encoding="utf-8")
    key = folder / "hmac.key"
    key.write_bytes(_KEY)
    units = credit_units(AUTOMATION_TUTOR, ledger, key, day)
    if units is None:
        msg = "demo ledger unreadable"
        raise RuntimeError(msg)
    return units


def _line(label: str, answers: dict[str, int], day: date) -> str:
    res = earned_time.resolve(answers, day)
    names = {t.earner.name for t in res.terms}
    if "automation" in names:
        term = res.term("automation")
        paid = f"automation +{term.gaming_minutes}g/+{term.shutdown_minutes}s"
    else:
        paid = "automation waived"  # ANKI_WAIVED_FROM..TUTOR_FROM
    return (
        f"{label:<44} {res.gaming_minutes:>4} min ({res.gaming_minutes / 60:.2f} h)"
        f"  {_hhmm(res.shutdown_minutes)}"
        f"  [{paid},"
        f" base {res.base.gaming_minutes}g/{_hhmm(res.base.shutdown_minutes)}]"
    )


def main() -> None:
    """Print the table."""
    eve = TUTOR_FROM - timedelta(days=1)
    _say(f"TUTOR_FROM = {TUTOR_FROM} (no first_credits: an unwired consumer)")
    _say(f"{'case':<44} {'gaming':>15}  shutdown")
    for done in (0, 1):
        answers = {**_OTHERS, "anki": done, "automation": done}
        _say(_line(f"{eve} eve: others + anki/automation={done}", answers, eve))
    nothing = {**_NONE, "anki": 0, "automation": 0}
    _say(_line(f"{eve} eve: nothing done", nothing, eve))
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        for blocks in (0, 1, 2, 4, 5):
            rows = [_block("s1", n, TUTOR_FROM) for n in range(1, blocks + 1)]
            units = _units(folder, rows, TUTOR_FROM)
            for others, tag in ((_OTHERS, "+ all others"), (_NONE, "tutor only")):
                answers = {**others, "automation": units}
                label = f"{TUTOR_FROM}: {blocks} rows -> {units} units, {tag}"
                _say(_line(label, answers, TUTOR_FROM))
        rows = [_block("s2", n, TUTOR_FROM) for n in range(1, 5)]
        detail = rows[2]["detail"]
        if not isinstance(detail, dict):
            msg = "demo row lost its detail"
            raise TypeError(msg)
        rows[2]["detail"] = {**detail, "active_seconds": 9000}  # edited after signing
        units = _units(folder, rows, TUTOR_FROM)
        label = f"{TUTOR_FROM}: 4 rows, 1 tampered -> {units} units"
        _say(_line(label, {**_OTHERS, "automation": units}, TUTOR_FROM))
        anki = {**_OTHERS, "anki": 1, "automation": 4}
        _say(
            _line(
                f"{TUTOR_FROM}: all + a stale anki answer (ignored)", anki, TUTOR_FROM
            )
        )
    _say(f"gaming ceiling {earned_time.GAMING_CEILING_MINUTES} min (8 h)")


if __name__ == "__main__":
    main()
