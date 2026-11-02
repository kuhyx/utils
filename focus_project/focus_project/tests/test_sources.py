# Copyright (c) 2026 Krzysztof Rudnicki
"""The adapter registry: clipping, inactive modules, fail-closed errors."""

from __future__ import annotations

from datetime import date
import logging
import sys
import types
from typing import TYPE_CHECKING

import pytest

from focus_project import sources
from focus_project._model import Project

if TYPE_CHECKING:
    from collections.abc import Callable

DAY = date(2026, 11, 2)
PROJECT = Project(
    id="p",
    name="P",
    start=DAY,
    end=DAY,
    replaces=("leetcode",),
    daily_minutes=120,
    unlock_minutes=30,
)


def _fake(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    fn: Callable[[date, Project], list[sources.Interval]],
) -> None:
    module = types.ModuleType(f"focus_project.sources.{name}")
    module.intervals = fn  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, f"focus_project.sources.{name}", module)


def _none(_day: date, _project: Project) -> list[sources.Interval]:
    return []


def test_day_bounds_is_24h_local() -> None:
    lo, hi = sources.day_bounds(DAY)
    assert hi - lo == 86400


def test_clip_limits_and_drops_empty() -> None:
    assert sources.clip([(0, 5), (4, 20), (30, 31), (9, 9)], (3, 10)) == [
        (3, 5),
        (4, 10),
    ]


def test_heartbeat_covers_previous_five_minutes() -> None:
    assert sources.heartbeat_interval(1000.0) == (700.0, 1000.0)


def test_collect_clips_to_the_day(monkeypatch: pytest.MonkeyPatch) -> None:
    lo, hi = sources.day_bounds(DAY)
    _fake(monkeypatch, "activity", lambda _d, _p: [(lo - 60, lo + 60), (hi, hi + 9)])
    _fake(monkeypatch, "leetcode", _none)
    _fake(monkeypatch, "browser", _none)
    assert sources.collect(DAY, PROJECT) == [(lo, lo + 60)]


def test_failing_source_contributes_zero_and_is_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    lo, _ = sources.day_bounds(DAY)

    def boom(_d: date, _p: Project) -> list[sources.Interval]:
        msg = "db locked"
        raise OSError(msg)

    _fake(monkeypatch, "activity", boom)
    _fake(monkeypatch, "leetcode", lambda _d, _p: [(lo, lo + 60)])
    _fake(monkeypatch, "browser", _none)
    with caplog.at_level(logging.ERROR):
        result = sources.collect_by_source(DAY, PROJECT)
    assert result["activity"] == []
    assert result["leetcode"] == [(lo, lo + 60)]
    assert "source activity: failed" in caplog.text


def test_missing_adapter_is_inactive_not_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake(monkeypatch, "activity", _none)
    monkeypatch.setattr(sources, "ADAPTERS", ("activity", "nonexistent"))
    assert "nonexistent" not in sources.collect_by_source(DAY, PROJECT)
