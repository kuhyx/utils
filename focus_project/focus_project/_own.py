# Copyright (c) 2026 Krzysztof Rudnicki
"""A project day's own worked minutes: the union of every source's intervals."""

from __future__ import annotations

from typing import TYPE_CHECKING

from focus_project import sources

if TYPE_CHECKING:
    from datetime import date

    from focus_project._model import Project


def union_seconds(spans: list[sources.Interval]) -> float:
    """Total length of the union of ``spans``."""
    total = 0.0
    end = float("-inf")
    for lo, hi in sorted(spans):
        if hi <= end:
            continue
        total += hi - max(lo, end)
        end = hi
    return total


def own_minutes_of(project: Project, day: date, moment: float) -> int:
    """Whole minutes worked on ``day``, uncapped, nothing after ``moment``."""
    spans = sources.clip(sources.collect(day, project), (float("-inf"), moment))
    return int(union_seconds(spans) // 60)
