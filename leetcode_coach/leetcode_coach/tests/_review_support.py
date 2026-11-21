"""Shared by the review tests: a fake guard CLI, the test key, a flagged row.

The three ``REAL_*`` values are read at import time, before the autouse
fixture in ``conftest.py`` repoints the seams, so a test can still name the
production default without ever using it.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any

from leetcode_coach import flagged, review_ledger

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

REVIEW_KEY = b"coach-test-key"
REAL_GUARD_COMMAND = flagged.GUARD_COMMAND
REAL_REVIEW_LEDGER = review_ledger.LEDGER_PATH
REAL_KEY_FILE = review_ledger.KEY_FILE


def flagged_row(slug: str = "two-sum") -> dict[str, Any]:
    """One row of the guard's ``--flagged --json`` report (measured 2026-11-21)."""
    return {
        "slug": slug,
        "accepted_at": "2026-11-21T18:01:34+01:00",
        "day": "2026-11-21",
        "active_seconds": 1500,
        "span_seconds": 2400,
        "tab_seconds": {"description": 1200, "solutions": 300},
        "failed": {"Wrong Answer": 2},
        "first_submission_active_seconds": 720,
        "theory": "done",
        "flagged": True,
    }


def fake_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *slugs: str,
    stdout: str | None = None,
    code: int = 0,
    sleep: float = 0,
) -> None:
    """Point the guard seam at a script that prints a report (or ``stdout``)."""
    report = {"flagged": [flagged_row(slug) for slug in slugs], "measured": []}
    text = json.dumps(report) if stdout is None else stdout
    script = tmp_path / "fake_guard.py"
    script.write_text(
        "import sys, time\n"
        f"time.sleep({sleep!r})\n"
        f"sys.stdout.write({text!r})\n"
        "sys.stderr.write('guard said no\\n')\n"
        f"sys.exit({code})\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(flagged, "GUARD_COMMAND", (sys.executable, str(script)))
