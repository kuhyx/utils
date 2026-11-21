"""The guard's flagged-solve report, read through the guard's own CLI.

A flagged solve took long although its theory was taught; `/leetcode review`
(DOCS-review.md) starts from that evidence. The coach may import only the four
guard modules `guard_bridge` allow-lists, so the report comes from running
``python3 -m leetcode_guard --flagged --json`` and parsing what it prints.

"Could not check" is not "nothing flagged": a guard that is missing, hangs,
exits non-zero or prints something else raises `CouldNotCheckError`. Only a
report whose ``flagged`` list is empty means there is nothing to review.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from typing import Any, Final

_LOG: Final = logging.getLogger(__name__)

GUARD_COMMAND: Final[tuple[str, ...]] = (
    sys.executable,
    *("-m", "leetcode_guard", "--flagged", "--json"),
)
"""The same interpreter the coach runs on: the guard is installed beside it."""
GUARD_TIMEOUT_SECONDS: Final = 30.0
_SECONDS_PER_MINUTE: Final = 60

Row = dict[str, Any]


class CouldNotCheckError(RuntimeError):
    """The guard gave no usable report; never the same as an empty one."""


def _fail(reason: str) -> CouldNotCheckError:
    _LOG.warning("guard flagged report unusable: %s", reason)
    return CouldNotCheckError(reason)


def flagged_rows() -> list[Row]:
    """The flagged solves, newest first, exactly as the guard reports them.

    Raises:
        CouldNotCheckError: when the guard CLI gave no usable report.
    """
    try:
        proc = subprocess.run(
            GUARD_COMMAND,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=GUARD_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        reason = f"the guard CLI did not run ({exc})"
        raise _fail(reason) from exc
    if proc.returncode != 0:
        last = (proc.stderr.strip().splitlines() or ["no message"])[-1]
        msg = f"the guard CLI failed (exit {proc.returncode}: {last})"
        raise _fail(msg)
    try:
        report = json.loads(proc.stdout)
    except ValueError as exc:
        reason = f"the guard CLI printed something that is not JSON ({exc})"
        raise _fail(reason) from exc
    rows = report.get("flagged") if isinstance(report, dict) else None
    if not isinstance(rows, list):
        msg = "the guard report has no flagged list"
        raise _fail(msg)
    if not all(isinstance(r, dict) and isinstance(r.get("slug"), str) for r in rows):
        msg = "the guard report has a flagged row without a slug"
        raise _fail(msg)
    return rows


def flagged_slugs() -> set[str]:
    """The slugs that can be reviewed right now (raises like `flagged_rows`)."""
    return {row["slug"] for row in flagged_rows()}


def _minutes(seconds: object) -> str:
    if not isinstance(seconds, int):
        return "n/a"
    return f"{round(seconds / _SECONDS_PER_MINUTE)}m"


def _pairs(value: object, *, timed: bool) -> str:
    if not isinstance(value, dict) or not value:
        return "none"
    shown = (f"{name} {_minutes(n) if timed else n}" for name, n in value.items())
    return ", ".join(shown)


def evidence_line(row: Row) -> str:
    """One flagged solve as the evidence a review starts from."""
    return (
        f"{row['slug']}  accepted {row.get('accepted_at', 'n/a')}"
        f"  active {_minutes(row.get('active_seconds'))}"
        f"  span {_minutes(row.get('span_seconds'))}"
        f"  failed {_pairs(row.get('failed'), timed=False)}"
        f"  first submit {_minutes(row.get('first_submission_active_seconds'))}"
        f"  tabs {_pairs(row.get('tab_seconds'), timed=True)}"
        f"  theory {row.get('theory', 'n/a')}"
    )
