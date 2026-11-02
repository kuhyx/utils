# Copyright (c) 2026 Krzysztof Rudnicki
"""record_activity, status, paths and the minutes stub."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path  # noqa: TC003
import threading

import pytest

import focus_project as fp
from focus_project import minutes
from focus_project._paths import data_dir

D1 = date(2026, 11, 2)


def _project() -> None:
    fp.create_project(
        "hr",
        name="HackerRank prep",
        start=D1,
        end=date(2026, 11, 5),
        replaces=["leetcode"],
        daily_minutes=120,
        unlock_minutes=30,
    )


def test_data_dir_env_and_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert data_dir() == tmp_path / "data"
    monkeypatch.delenv("FOCUS_PROJECT_DATA")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert data_dir() == tmp_path / "home" / ".local" / "share" / "focus_project"


def test_record_activity_line(data: Path) -> None:
    _project()
    fp.record_activity(
        "timer", "start", ts=1_000.5, project="hr", dev="phone", meta={"k": 1}
    )
    row = json.loads((data / "activity.jsonl").read_text())
    assert row == {
        "ts": 1_000.5,
        "source": "timer",
        "kind": "start",
        "project": "hr",
        "dev": "phone",
        "meta": {"k": 1},
    }


def test_record_activity_defaults_now_and_project(data: Path) -> None:
    today = date.today()  # noqa: DTZ011
    fp.create_project(
        "now",
        name="n",
        start=today,
        end=today,
        replaces=["tutor"],
        daily_minutes=60,
        unlock_minutes=10,
    )
    fp.record_activity("tutor", "heartbeat")
    fp.record_activity("tutor", "heartbeat", project=None)
    rows = [json.loads(x) for x in (data / "activity.jsonl").read_text().splitlines()]
    assert [r["project"] for r in rows] == ["now", "now"]
    assert rows[0]["ts"] > 1_700_000_000
    assert rows[0]["meta"] == {}
    assert rows[0]["dev"] == "pc"


def test_record_activity_no_project_when_none_active(data: Path) -> None:
    fp.record_activity("browser", "heartbeat", ts=1_000.0)
    assert json.loads((data / "activity.jsonl").read_text())["project"] is None


@pytest.mark.parametrize(
    "kw",
    [
        {"source": "x", "kind": "start"},
        {"source": "timer", "kind": "x"},
        {"source": "timer", "kind": "start", "dev": "tv"},
    ],
)
def test_record_activity_validation(kw: dict[str, str], data: Path) -> None:
    with pytest.raises(ValueError, match="unknown"):
        fp.record_activity(**kw)  # type: ignore[arg-type]
    assert not (data / "activity.jsonl").exists()


def test_record_activity_concurrent_appends(data: Path) -> None:
    def work(n: int) -> None:
        for i in range(20):
            fp.record_activity(
                "tutor", "heartbeat", ts=float(n * 100 + i), meta={"pad": "x" * 5000}
            )

    threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    lines = (data / "activity.jsonl").read_text().splitlines()
    assert len(lines) == 160
    assert all(json.loads(x)["source"] == "tutor" for x in lines)


def test_status_active_uses_minutes_module(monkeypatch: pytest.MonkeyPatch) -> None:
    _project()
    assert fp.status(D1)["minutes"] == 0  # the stub
    monkeypatch.setattr(minutes, "minutes_for", lambda _day: 45)
    st = fp.status(D1)
    assert st == {
        "project": "hr",
        "name": "HackerRank prep",
        "minutes": 45,
        "daily_minutes": 120,
        "unlock_minutes": 30,
        "ends": "2026-11-05",
        "replaces": ["leetcode"],
    }


def test_status_inactive() -> None:
    st = fp.status(D1)
    assert st["project"] is None
    assert st["minutes"] == 0
    assert st["replaces"] == []
    assert st["ends"] is None
    assert set(st) == {
        "project",
        "name",
        "minutes",
        "daily_minutes",
        "unlock_minutes",
        "ends",
        "replaces",
    }


def test_minutes_for_exported() -> None:
    assert fp.minutes_for(D1) == 0
