# Copyright (c) 2026 Krzysztof Rudnicki
"""status(day) carries the milestones for i3bar / daily-limits / tutor."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import focus_project as fp
from focus_project import _clock, evidence
from focus_project.tests.helpers import at, make

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _now(monkeypatch: pytest.MonkeyPatch, day: int, hour: int) -> None:
    stamp = at(day, hour).timestamp()
    monkeypatch.setattr(_clock, "now", lambda: stamp)


def test_idle_status_has_the_keys() -> None:
    snap = fp.status(date(2026, 11, 10))
    assert snap["milestones"] == []
    assert snap["missed"] is False


def test_status_lists_milestones_and_goes_red(monkeypatch: pytest.MonkeyPatch) -> None:
    make()
    _now(monkeypatch, 10, 9)
    snap = fp.status(date(2026, 11, 10))
    assert snap["missed"] is False
    assert snap["milestones"][0]["id"] == "rules"
    assert set(snap["milestones"][0]) == {"id", "due", "state"}
    _now(monkeypatch, 11, 9)
    snap = fp.status(date(2026, 11, 11))
    assert snap["missed"] is True
    assert snap["milestones"][0]["state"] == "missed"
    assert snap["milestones"][0]["due"] == "2026-11-10T23:59:00"


def test_status_stays_red_on_test_day(monkeypatch: pytest.MonkeyPatch) -> None:
    make()
    _now(monkeypatch, 27, 9)
    assert fp.status(date(2026, 11, 27))["missed"] is True
    assert fp.owed_lock(at(27, 9)) is None


def test_status_survives_unreadable_evidence(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    make()
    _now(monkeypatch, 11, 9)

    def boom(project_id: str) -> list[evidence.Evidence]:
        msg = "disk"
        raise OSError(msg)

    monkeypatch.setattr(evidence, "read", boom)
    with caplog.at_level("WARNING"):
        snap = fp.status(date(2026, 11, 11))
    assert snap["milestones"] == []
    assert snap["missed"] is False
    assert "evidence unreadable" in caplog.text
    assert fp.owed_lock(at(11, 9)) is None


def test_isolation_canary(tmp_path: Path) -> None:
    make()
    assert not (tmp_path / "data" / "evidence").exists()
