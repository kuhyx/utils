"""Tests for cluster progress and the +3/+10 day re-test schedule (decisions 10, 12).

Progress is derived from the session logs alone: a problem is *started* once it
has a ``code`` event and *solved* once it has a ``code`` and a ``postmortem``.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import TYPE_CHECKING

from leetcode_coach import progress

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

DAY0 = dt.date(2026, 10, 20)

DECISION_10 = {
    "bit-cancellation": [268, 260, 169, 137],
    "two-pointers": [167, 15, 11, 42],
    "sliding-window": [3, 424, 567, 76],
    "prefix-sum-hash": [560, 523, 974, 525],
    "monotonic-stack": [739, 496, 503, 84],
    "intervals": [56, 57, 435, 452],
}


def log(directory: Path, day: dt.date, slug: str, *events: object) -> Path:
    """Append events (dicts, or raw strings for torn lines) to a session file."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{day.isoformat()}-{slug}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        for event in events:
            fh.write((event if isinstance(event, str) else json.dumps(event)) + "\n")
    return path


def solve(directory: Path, day: dt.date, slug: str) -> None:
    log(directory, day, slug, {"event": "code", "ts": "x"}, {"event": "postmortem"})


def test_clusters_json_is_decision_10_verbatim() -> None:
    clusters = progress.load_clusters()
    assert {name: [p["id"] for p in ps] for name, ps in clusters.items()} == (
        DECISION_10
    )
    assert list(clusters) == list(DECISION_10)
    assert clusters["bit-cancellation"][0]["slug"] == "missing-number"


def test_cluster_of_names_the_owning_cluster() -> None:
    assert progress.cluster_of("single-number-iii") == "bit-cancellation"
    assert progress.cluster_of("two-sum") is None


def test_sessions_dir_is_overridable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(progress.SESSIONS_ENV, str(tmp_path))
    assert progress.sessions_dir() == tmp_path
    monkeypatch.delenv(progress.SESSIONS_ENV)
    assert progress.sessions_dir().parts[-3:] == (
        "share",
        "leetcode-coach",
        "sessions",
    )


def test_a_solve_is_due_three_days_later_not_two(tmp_path: Path) -> None:
    solve(tmp_path, DAY0, "missing-number")
    assert progress.due_retests(tmp_path, today=DAY0 + dt.timedelta(days=2)) == []
    assert progress.due_retests(tmp_path, today=DAY0 + dt.timedelta(days=3)) == [
        {
            "slug": "missing-number",
            "cluster": "bit-cancellation",
            "stage": 1,
            "due": "2026-10-23",
            "solved": "2026-10-20",
        }
    ]


def test_code_without_postmortem_is_not_solved(tmp_path: Path) -> None:
    log(tmp_path, DAY0, "two-sum", {"event": "code"}, {"event": "rung", "rung": "H1"})
    assert progress.due_retests(tmp_path, today=DAY0 + dt.timedelta(days=30)) == []


def test_the_second_retest_waits_for_day_ten_and_then_none(tmp_path: Path) -> None:
    solve(tmp_path, DAY0, "two-sum")
    later = DAY0 + dt.timedelta(days=4)
    log(tmp_path, later, "two-sum", {"event": "code"}, {"event": "postmortem"})
    log(tmp_path, later, "two-sum", {"event": "retest", "stage": 1})
    assert progress.due_retests(tmp_path, today=DAY0 + dt.timedelta(days=9)) == []
    due = progress.due_retests(tmp_path, today=DAY0 + dt.timedelta(days=10))
    assert [(r["stage"], r["due"], r["solved"], r["cluster"]) for r in due] == [
        (2, "2026-10-30", "2026-10-20", None)
    ]
    log(tmp_path, DAY0 + dt.timedelta(days=11), "two-sum", {"event": "retest"})
    assert progress.due_retests(tmp_path, today=DAY0 + dt.timedelta(days=99)) == []


def test_solve_spread_over_two_days_dates_from_the_postmortem(tmp_path: Path) -> None:
    log(tmp_path, DAY0, "3sum", {"event": "code"})
    log(tmp_path, DAY0 + dt.timedelta(days=1), "3sum", {"event": "postmortem"})
    assert progress.history("3sum", tmp_path).solved == DAY0 + dt.timedelta(days=1)


def test_due_rows_are_ordered_by_due_date(tmp_path: Path) -> None:
    solve(tmp_path, DAY0 + dt.timedelta(days=1), "b-problem")
    solve(tmp_path, DAY0, "a-problem")
    due = progress.due_retests(tmp_path, today=DAY0 + dt.timedelta(days=5))
    assert [r["slug"] for r in due] == ["a-problem", "b-problem"]


def test_junk_is_skipped_with_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    solve(tmp_path, DAY0, "missing-number")
    log(tmp_path, DAY0, "missing-number", "{torn", "[1]", "", {"no": "event"})
    (tmp_path / "notes.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "2026-13-40-bad-date.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "2026-10-20-broken.jsonl").write_bytes(b"\xff\xfe")
    with caplog.at_level(logging.WARNING):
        due = progress.due_retests(tmp_path, today=DAY0 + dt.timedelta(days=3))
    assert [r["slug"] for r in due] == ["missing-number"]
    assert "not JSON" in caplog.text
    assert "unreadable" in caplog.text


def test_a_missing_directory_has_no_history(tmp_path: Path) -> None:
    assert progress.due_retests(tmp_path / "absent", today=DAY0) == []
    assert progress.history("x", tmp_path / "absent") == progress.History(
        started=False, solved=None, retests=0
    )


def test_default_today_and_directory_come_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(progress.SESSIONS_ENV, str(tmp_path))
    solve(tmp_path, progress.local_today() - dt.timedelta(days=3), "missing-number")
    assert [r["slug"] for r in progress.due_retests()] == ["missing-number"]
    assert progress.cluster_progress()["bit-cancellation"]["solved"] == 1


def test_cluster_progress_counts_started_and_solved(tmp_path: Path) -> None:
    solve(tmp_path, DAY0, "missing-number")
    log(tmp_path, DAY0, "single-number-iii", {"event": "code"})
    for slug in ("merge-intervals", "insert-interval", "non-overlapping-intervals"):
        solve(tmp_path, DAY0, slug)
    solve(tmp_path, DAY0, "minimum-number-of-arrows-to-burst-balloons")
    clusters = progress.cluster_progress(tmp_path)
    assert clusters["bit-cancellation"] == {
        "total": 4,
        "started": 2,
        "solved": 1,
        "next": "majority-element",
    }
    assert clusters["intervals"] == {
        "total": 4,
        "started": 4,
        "solved": 4,
        "next": None,
    }
    assert clusters["two-pointers"]["next"] == "two-sum-ii-input-array-is-sorted"


def test_next_new_skips_accepted_problems(tmp_path: Path) -> None:
    solve(tmp_path, DAY0, "missing-number")
    asked: list[str] = []

    def accepted(slug: str) -> bool:
        asked.append(slug)
        return slug == "single-number-iii"

    assert progress.next_new("bit-cancellation", tmp_path, accepted) == (
        "majority-element"
    )
    assert asked == ["single-number-iii", "majority-element"]
    assert progress.next_new("bit-cancellation", tmp_path, lambda _s: True) is None


def test_append_event_writes_todays_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(progress.SESSIONS_ENV, str(tmp_path / "new"))
    path = progress.append_event("two-sum", {"event": "retest", "stage": 1})
    assert path.name == f"{progress.local_today().isoformat()}-two-sum.jsonl"
    event = json.loads(path.read_text(encoding="utf-8"))
    assert event["event"] == "retest"
    assert dt.datetime.fromisoformat(event["ts"]).tzinfo is not None
    assert progress.count_events("two-sum", "retest", tmp_path / "new") == 1
