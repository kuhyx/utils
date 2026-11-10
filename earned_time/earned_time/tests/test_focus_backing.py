# Copyright (c) 2026 Krzysztof Rudnicki
"""Regression: a timer-only focus day after the anti-cheat cutover pays 0.

Runs the REAL ``focus_project`` (the sibling package of this monorepo):
timer rows -> harvester -> signed ledger -> ``credit_units``. earned_time
itself does not change; this pins that the gate reaches pay.
"""

from __future__ import annotations

from datetime import date, datetime
import importlib
import json
from pathlib import Path
import sys
from typing import TYPE_CHECKING

import pytest

from earned_time import credit_units, earners_for

if TYPE_CHECKING:
    from types import ModuleType

DAY = date(2026, 11, 9)  # after focus_project.BACKING_FROM
_SIBLING = Path(__file__).resolve().parents[3] / "focus_project"


def at(hour: int, minute: int) -> float:
    return datetime(2026, 11, 9, hour, minute).astimezone().timestamp()


@pytest.fixture
def real_fp(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, key_file: Path
) -> ModuleType:
    """The real focus_project on redirected state (HOME, data dir, key)."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("FOCUS_PROJECT_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("FOCUS_PROJECT_KEY", str(key_file))
    monkeypatch.setenv("FOCUS_PROJECT_LEETCODE_LEDGER", str(tmp_path / "lc.json"))
    monkeypatch.delitem(sys.modules, "focus_project")  # the conftest's fake
    monkeypatch.syspath_prepend(str(_SIBLING))
    fp = importlib.import_module("focus_project")
    fp.create_project(
        "hr",
        name="HR",
        start=DAY,
        end=DAY,
        replaces=["leetcode"],
        daily_minutes=120,
        unlock_minutes=30,
    )
    return fp


def pay(fp: ModuleType, tmp_path: Path, key_file: Path, *rows: object) -> int | None:
    log = tmp_path / "data" / "activity.jsonl"
    log.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    harvest = importlib.import_module("focus_project.harvest")
    assert harvest.harvest(now=at(23, 0)) == 0
    (item,) = (e for e in earners_for(DAY) if e.name == "focus")
    return credit_units(item, tmp_path / "data" / "ledger.json", key_file, DAY)


def row(source: str, kind: str, ts: float) -> dict[str, object]:
    return {"ts": ts, "source": source, "kind": kind, "project": "hr"}


TIMER = (
    row("timer", "start", at(9, 0)),
    row("timer", "checkin", at(9, 5)),
    row("timer", "stop", at(9, 10)),
)


def test_timer_only_day_pays_zero(
    real_fp: ModuleType, tmp_path: Path, key_file: Path
) -> None:
    assert date(2026, 11, 8) == real_fp.BACKING_FROM
    assert pay(real_fp, tmp_path, key_file, *TIMER) == 0


def test_backed_timer_day_still_pays(
    real_fp: ModuleType, tmp_path: Path, key_file: Path
) -> None:
    beat = row("tutor", "heartbeat", at(9, 5))
    assert pay(real_fp, tmp_path, key_file, *TIMER, beat) == 10
