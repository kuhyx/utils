# Copyright (c) 2026 Krzysztof Rudnicki
"""Fakes for the focus tests: a fake ``focus_project`` and signed focus rows."""

from __future__ import annotations

from datetime import date, timedelta
import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING

from earned_time import FocusEarner, earners_for
from earned_time.tests._maturity_rows import at, signed

if TYPE_CHECKING:
    import pytest

START = date(2026, 11, 2)
DAY = START + timedelta(days=1)


def project(**changes: object) -> SimpleNamespace:
    """A fake ``focus_project.Project`` (the contract's fields)."""
    fields: dict[str, object] = {
        "start": START,
        "end": START + timedelta(days=3),
        "replaces": ("leetcode", "reading", "tutor"),
        "daily_minutes": 120,
    }
    return SimpleNamespace(**{**fields, **changes})


def activate(monkeypatch: pytest.MonkeyPatch, active: object) -> None:
    """Make ``focus_project.active`` return ``active`` on project days only."""

    def on(day: date) -> object:
        return active if START <= day <= START + timedelta(days=3) else None

    monkeypatch.setitem(sys.modules, "focus_project", SimpleNamespace(active=on))


def row(
    minutes: object, n: int, day: date = DAY, **detail: object
) -> dict[str, object]:
    """A signed focus credit row ending at noon on ``day``."""
    return signed(
        {
            "kind": "credit",
            "entry_id": f"hr-{day:%Y%m%d}-m{n}",
            "day": day.isoformat(),
            "detail": {"minutes": minutes, "ended_at": at(day), **detail},
        }
    )


def focus(monkeypatch: pytest.MonkeyPatch, **changes: object) -> FocusEarner:
    """Today's focus earner under a fake project."""
    activate(monkeypatch, project(**changes))
    (found,) = (e for e in earners_for(DAY) if e.name == "focus")
    assert isinstance(found, FocusEarner)
    return found
