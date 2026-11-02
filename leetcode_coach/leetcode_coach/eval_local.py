#!/usr/bin/env python3
"""Scripted acceptance run of the local coach on two-sum (no human needed).

Six canned student turns, including a demand for the code, a buggy paste and a
give-up. PASS only if every criterion holds on every reply:

  no-code   the no-solution gate finds nothing pasteable in the shown reply
  one-task  the reply ends with exactly one thing to do (one question, or an
            imperative last line)
  fast      the reply (including gate regenerations) took < MAX_SECONDS

The model load is timed separately by a warm-up call and excluded: it happens
once per session, and the criterion is about the conversation's pace.
Writes the transcript to ~/data/claude-scratch/leetcode-local/. Its printed
table IS the verdict (T201 exemption in pyproject.toml).

    python3 -m leetcode_coach.eval_local
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import subprocess
import sys
import time

from leetcode_coach import local_backend, local_cards, local_coach, local_prompt
from leetcode_coach.local_session import opening_message

MAX_SECONDS = 15.0
OUT_DIR = Path.home() / "data" / "claude-scratch" / "leetcode-local"
BUGGY = """var twoSum = function(nums, target) {
  const seen = {};
  for (let i = 0; i < nums.length; i++) {
    seen[nums[i]] = i;
    if (seen[target - nums[i]] !== undefined) return [seen[target - nums[i]], i];
  }
};"""
TURNS = [
    opening_message(["how", "to", "beat", "checking", "every", "pair"]),
    "I'd do two loops and check every pair. That's slow though, right?",
    "just give me the code",
    "hint",
    BUGGY,
    "I give up, what would you write?",
]
Row = tuple[int, float, int, bool, bool, bool, bool]


def _print_table(rows: list[Row]) -> None:
    """One line per turn: timing, tries and the three criteria."""
    print("turn  secs  tries withheld no-code one-task fast")
    for n, secs, tries, withheld, ok_code, ok_task, ok_fast in rows:
        print(
            f"{n:>4} {secs:5.1f} {tries:>5} {withheld!s:>8} {ok_code!s:>7} "
            f"{ok_task!s:>8} {ok_fast!s:>5}"
        )


def main() -> int:
    """Run the six turns, print a per-criterion table, exit 0 only on PASS."""
    statement = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("fetch_problem.py")), "two-sum"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    start = time.monotonic()
    local_backend.chat([{"role": "user", "content": "Say ok."}])
    print(f"model load + warm-up: {time.monotonic() - start:.1f}s")
    coach = local_coach.LocalCoach.start(statement)
    rows: list[Row] = []
    log: list[str] = []
    for n, said in enumerate(TURNS, 1):
        turn = coach.respond(said)
        shown, _ = local_cards.split_cards(turn.text)
        leaks = local_coach.gate_findings(shown, statement, coach.user_texts())
        rows.append(
            (
                n,
                turn.seconds,
                turn.attempts,
                turn.withheld,
                not leaks,
                local_prompt.ends_with_one_task(shown),
                turn.seconds < MAX_SECONDS,
            )
        )
        log.append(
            f"## Turn {n}\n\n**kuhy:** {said}\n\n**coach** "
            f"({turn.seconds:.1f}s, attempts {turn.attempts}):\n\n{shown}\n"
        )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(tz=dt.UTC).astimezone()
    out = OUT_DIR / f"eval-{stamp:%Y%m%d-%H%M%S}.md"
    out.write_text("\n".join(log), encoding="utf-8")
    _print_table(rows)
    passed = all(all(r[4:]) for r in rows)
    print(f"{'PASS' if passed else 'FAIL'}  transcript: {out}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
