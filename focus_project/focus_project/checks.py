# Copyright (c) 2026 Krzysztof Rudnicki
"""Pluggable check sources for the auto-checked milestones, and latching.

A source is ``fn(project, now) -> True | False | None``; ``None`` means "could
not check" (logged) and counts as not done. Only ``phone`` is auto-checked
(the calendar slot check was dropped, 2026-11-10: ``slot`` is two taps).

:func:`run_checks` is the only place sources run: status()/milestones() stay
cheap and read the latched ``check`` rows it appends (only on a change).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import logging

from focus_project import _milestones, _mutate, _store, evidence
from focus_project._model import Project

_LOG = logging.getLogger(__name__)
CheckSource = Callable[[Project, datetime], bool | None]
DAY_MS = 24 * 3600 * 1000
# A phone check starts 24 h before the milestone is due.
WINDOW = timedelta(hours=24)


def _report_ok(value: object, report_ms: int) -> bool:
    """A plan exists, cards are due, the phone was seen <= 24 h before the report."""
    if not isinstance(value, dict):
        return False
    try:
        return bool(
            value["plan"] is True
            and int(value["due"]) > 0
            and report_ms - int(value["seen_ms"]) <= DAY_MS
        )
    except KeyError, TypeError, ValueError:
        return False


def phone_source(project: Project, now: datetime) -> bool | None:
    """Read tutor's latest ``phone_check`` report (<= 24 h old).

    No report, a stale one or one stamped ahead of the clock = ``None``
    (the worker is not reporting). A fresh one passes only if the plan
    exists, cards are due and the phone was seen within 24 h of the report.
    """
    report = evidence.last(evidence.read(project.id), "phone", "phone_check")
    if report is None:
        _LOG.warning("phone check: no tutor report for %s", project.id)
        return None
    if not 0 <= evidence.to_ms(now) - report.ms <= DAY_MS:
        _LOG.warning("phone check: tutor report for %s is stale or ahead", project.id)
        return None
    return _report_ok(report.value, report.ms)


SOURCES: dict[str, CheckSource] = {"phone": phone_source}


def register_source(name: str, source: CheckSource) -> None:
    """Replace the callable behind an auto check (``phone``)."""
    if name not in SOURCES:
        msg = f"unknown check source {name!r}; known: {sorted(SOURCES)}"
        raise ValueError(msg)
    SOURCES[name] = source


def _run(project: Project, now: datetime) -> bool | None:
    try:
        return SOURCES["phone"](project, now)
    except Exception as exc:  # noqa: BLE001 (pluggable code: any failure = unknown)
        _LOG.warning("phone check source failed: %s", exc)
        return None


def run_checks(
    project_id: str, *, now: datetime | None = None
) -> dict[str, bool | None]:
    """Run the auto checks of open phone milestones; latch what changed.

    Returns milestone id -> verdict for the ones checked (inside their
    24 h window, not yet done). KeyError for an unknown project; a focus
    project has nothing to check.
    """
    stamp = _mutate.local_now(now)
    project = next((p for p in _store.read_all() if p.id == project_id), None)
    if project is None:
        raise KeyError(project_id)
    open_ids = [
        m.id
        for m in _milestones.milestones(project, stamp)
        if m.id.startswith("phone:")
        and m.state not in {"done", "late_done"}
        and stamp >= m.due - WINDOW
    ]
    if not open_ids:
        return {}
    verdict = _run(project, stamp)
    rows = evidence.read(project_id)
    for mid in open_ids:
        _, latest, seen = evidence.check_summary(rows, mid)
        if verdict != latest and not (verdict is None and not seen):
            evidence.append(project_id, mid, "check", verdict, stamp)
    return dict.fromkeys(open_ids, verdict)
