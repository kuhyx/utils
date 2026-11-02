# Copyright (c) 2026 Krzysztof Rudnicki
"""Adapter for accepted LeetCode submissions (leetcode-guard's ledger).

Read-only. Each accepted submission (``ac:<id>`` credit row, HMAC verified)
is a heartbeat at ``detail.submitted_at``, so it covers the five minutes
before it. The window is deliberately NOT longer: the time spent reading and
thinking on the site is the browser adapter's to count, and a submission
alone proves only that work happened, not for how long. Applies only to a
project whose ``site_patterns`` name leetcode; any other project is not
LeetCode practice. No readable signing key: contributes nothing (logged).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

import earned_time

from focus_project import ledger
from focus_project.sources import Interval, heartbeat_interval

if TYPE_CHECKING:
    from datetime import date

    from focus_project._model import Project

LEDGER_ENV = "FOCUS_PROJECT_LEETCODE_LEDGER"
_LOG = logging.getLogger(__name__)


def ledger_file() -> Path:
    """leetcode-guard's ledger, or the test override."""
    override = os.environ.get(LEDGER_ENV)
    if override:
        return Path(override)
    return Path.home() / ".local" / "share" / "leetcode_guard" / "ledger.json"


def _submitted_at(row: object, key: bytes) -> float | None:
    """The submission time of a verified accepted-submission row, else None."""
    if not (
        isinstance(row, dict)
        and row.get("kind") == "credit"
        and str(row.get("entry_id", "")).startswith("ac:")
        and earned_time.verified(row, key)
    ):
        return None
    detail = row.get("detail")
    try:
        return float(detail["submitted_at"])  # type: ignore[index]
    except KeyError, TypeError, ValueError:
        return None


def intervals(day: date, project: Project) -> list[Interval]:  # noqa: ARG001
    """One heartbeat per accepted submission (the registry clips to the day)."""
    if not any("leetcode" in pattern.lower() for pattern in project.site_patterns):
        return []
    key = ledger.read_key()
    if key is None:
        _LOG.warning("leetcode source: no signing key, contributes 0")
        return []
    stamps = (_submitted_at(row, key) for row in ledger.read_rows(ledger_file()))
    return [heartbeat_interval(ts) for ts in stamps if ts is not None]
