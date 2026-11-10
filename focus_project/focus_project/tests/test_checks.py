# Copyright (c) 2026 Krzysztof Rudnicki
"""Pluggable check sources, the phone source, and latching."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

import focus_project as fp
from focus_project import _paths, checks, evidence
from focus_project.tests.helpers import SAT1, at, make

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

MID = "phone:2026-11-14"


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _report(
    moment: datetime,
    *,
    plan: bool = True,
    due: int = 5,
    seen: datetime | None = None,
) -> None:
    value = {"plan": plan, "due": due, "seen_ms": _ms(seen or moment)}
    fp.record_evidence("iv", "phone", "phone_check", value, now=moment)


def _phone(now: datetime) -> bool | None:
    return checks.phone_source(fp.list_projects()[0], now)


def test_phone_source_without_a_report_is_unknown(
    caplog: pytest.LogCaptureFixture,
) -> None:
    make()
    with caplog.at_level("WARNING"):
        assert _phone(at(13, 9)) is None
    assert "phone" in caplog.text


def test_phone_source_passes_on_a_fresh_good_report() -> None:
    make()
    _report(at(13, 8), seen=at(12, 20))
    assert _phone(at(13, 9)) is True


@pytest.mark.parametrize(
    "bad",
    [{"plan": False}, {"due": 0}, {"seen": at(11, 7)}],
)
def test_phone_source_fails_on_any_bad_part(bad: dict[str, object]) -> None:
    make()
    _report(at(13, 8), **bad)  # type: ignore[arg-type]
    assert _phone(at(13, 9)) is False


def test_phone_source_stale_or_future_report_is_unknown() -> None:
    make()
    _report(at(13, 8))
    assert _phone(at(14, 8, 1)) is None  # the worker stopped reporting
    assert _phone(at(13, 7)) is None  # stamped ahead of the clock


def test_phone_source_uses_the_latest_report() -> None:
    make()
    _report(at(13, 8), plan=False)
    _report(at(13, 9))
    assert _phone(at(13, 10)) is True


def test_phone_source_hand_edited_row_is_a_failure() -> None:
    make()
    _report(at(13, 8))
    path = _paths.evidence_path("iv")
    row = {"ms": _ms(at(13, 9)), "milestone": "phone", "kind": "phone_check"}
    path.write_text(path.read_text() + json.dumps({**row, "value": "ok"}) + "\n")
    assert _phone(at(13, 10)) is False


def _patch(
    monkeypatch: pytest.MonkeyPatch, fn: Callable[[fp.Project, datetime], bool | None]
) -> None:
    monkeypatch.setitem(checks.SOURCES, "phone", fn)


def _trip_project() -> None:
    make()
    fp.answer_weekend("iv", SAT1, trip=True, now=at(11, 9))


def test_run_checks_latches_a_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    _trip_project()
    _patch(monkeypatch, lambda p, n: True)
    assert fp.run_checks("iv", now=at(13, 9)) == {MID: True}
    assert fp.run_checks("iv", now=at(13, 10)) == {MID: True}
    rows = [r for r in evidence.read("iv") if r.kind == "check"]
    assert [(r.milestone, r.value) for r in rows] == [(MID, True)]


def test_run_checks_only_inside_the_window(monkeypatch: pytest.MonkeyPatch) -> None:
    _trip_project()
    _patch(monkeypatch, lambda p, n: True)
    assert fp.run_checks("iv", now=at(12, 11, 59)) == {}  # >24 h before due
    assert fp.run_checks("iv", now=at(12, 12)) == {MID: True}


def test_run_checks_records_changes_not_every_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _trip_project()
    answers: list[bool | None] = [None, False, False, None, None]
    _patch(monkeypatch, lambda p, n: answers.pop(0))
    for minute in range(5):
        fp.run_checks("iv", now=at(13, 9, minute))
    rows = [r.value for r in evidence.read("iv") if r.kind == "check"]
    assert rows == [False, None]  # leading None writes nothing


def test_run_checks_source_crash_is_unknown_and_loud(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _trip_project()

    def boom(p: fp.Project, n: datetime) -> bool:
        msg = "tutor down"
        raise OSError(msg)

    _patch(monkeypatch, boom)
    with caplog.at_level("WARNING"):
        assert fp.run_checks("iv", now=at(13, 9)) == {MID: None}
    assert "tutor down" in caplog.text


def test_run_checks_skips_finished_milestones(monkeypatch: pytest.MonkeyPatch) -> None:
    _trip_project()
    fp.record_evidence("iv", MID, "tap", value=True, now=at(12, 9))
    evidence.append("iv", MID, "check", True, at(12, 10))
    _patch(monkeypatch, lambda p, n: pytest.fail("already done"))
    assert fp.run_checks("iv", now=at(13, 9)) == {}


def test_run_checks_ignores_focus_projects() -> None:
    fp.create_project(
        "f",
        name="F",
        start=at(10).date(),
        end=at(12).date(),
        replaces=["leetcode"],
        daily_minutes=30,
        unlock_minutes=10,
    )
    assert fp.run_checks("f", now=at(11, 9)) == {}
    with pytest.raises(KeyError):
        fp.run_checks("ghost", now=at(11, 9))


def test_register_source_swaps_the_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(checks, "SOURCES", dict(checks.SOURCES))

    def fn(p: fp.Project, n: datetime) -> bool:
        return True

    fp.register_source("phone", fn)
    assert checks.SOURCES["phone"] is fn
    with pytest.raises(ValueError, match="source"):
        fp.register_source("calendar", fn)


def test_end_to_end_phone_milestone_goes_done() -> None:
    _trip_project()
    fp.record_evidence("iv", MID, "tap", value=True, now=at(12, 9))
    _report(at(13, 9))
    assert fp.run_checks("iv", now=at(13, 9, 30)) == {MID: True}
    state = {m.id: m.state for m in fp.milestones(fp.list_projects()[0], at(13, 10))}
    assert state[MID] == "done"


def test_report_missing_a_field_fails() -> None:
    make()
    path = _paths.evidence_path("iv")
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"ms": _ms(at(13, 8)), "milestone": "phone", "kind": "phone_check"}
    path.write_text(json.dumps({**row, "value": {"plan": True}}) + "\n")
    assert _phone(at(13, 9)) is False
