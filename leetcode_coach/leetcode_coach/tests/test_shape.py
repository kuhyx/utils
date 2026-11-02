"""Q5: SQL problems ask for the OUTPUT SHAPE, algorithm problems keep ``req:``."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, NoReturn

import pytest

from leetcode_coach import phase, req_check, session_log, shape, toolbox
from leetcode_coach.relay import grading
from leetcode_coach.tests._relay_direct import FakeAsk, grade, make_coach, started
from leetcode_coach.tests._relay_statements import MISSING_NUMBER

if TYPE_CHECKING:
    from pathlib import Path

SQL_STATEMENT = """# 1179. Reformat Department Table (Easy)
Tags: Database
Languages available: mysql, mssql, oraclesql, postgresql, pythondata

Reformat the table so there is a department id column and a revenue column
for each month.
"""
SHAPE = "shape: columns id plus Jan_Revenue..Dec_Revenue, one row per department id"
QUERY = "SELECT id, SUM(CASE WHEN month = 'Jan' THEN revenue END) FROM Department GROUP BY id;"


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        (SQL_STATEMENT, True),
        ("# 176. Second Highest Salary (Medium)\nTags: Database\n", True),
        ("# 1. X (Easy)\nTags: Array\nLanguages available: mysql, python3\n", True),
        (MISSING_NUMBER, False),
        ("missing-number", False),
        ("", False),
    ],
)
def test_is_sql(statement: str, expected: bool) -> None:
    assert shape.is_sql(statement) is expected


@pytest.mark.parametrize(
    ("text", "missing"),
    [
        (SHAPE, ()),
        ("shape: two columns, name and total; a row per customer, grouped by name", ()),
        ("shape: the columns are id and name", ("rows", "grouping")),
        ("shape: one row per id", ("columns",)),
        ("shape: nothing yet", ("columns", "rows", "grouping")),
    ],
)
def test_missing_facets(text: str, missing: tuple[str, ...]) -> None:
    assert shape.missing_facets(text) == missing


def test_check_is_a_req_check_result_without_a_model() -> None:
    assert shape.check(SHAPE) == req_check.Check("pass", (), "shape")
    assert shape.check("shape: columns id") == req_check.Check(
        "incomplete", ("rows", "grouping"), "shape"
    )


def _gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str
) -> phase.PhaseGate:
    def never(*_a: object) -> NoReturn:
        pytest.fail("a SQL shape must never reach the requirement checker")

    monkeypatch.setattr(req_check, "check", never)
    return phase.PhaseGate(tmp_path / "log.jsonl", toolbox.load_safe(), lambda: text)


def _events(gate: phase.PhaseGate) -> list[str]:
    return [e["event"] for e in session_log.read(gate.log)]


def test_sql_code_is_held_back_until_a_shape_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = _gate(tmp_path, monkeypatch, SQL_STATEMENT)
    sent, note = gate.screen(QUERY)
    assert sent is None
    assert "shape:" in note
    assert "req:" not in note
    assert _events(gate) == []
    sent, note = gate.screen(SHAPE)
    assert sent == f"{SHAPE}\n\n[req check: pass]"
    assert "output shape accepted" in note
    assert gate.screen(QUERY) == (QUERY, "")
    assert _events(gate) == ["req", "req_check", "code"]
    assert session_log.read(gate.log)[1]["via"] == "shape"


def test_a_req_list_on_a_sql_problem_counts_as_the_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = _gate(tmp_path, monkeypatch, SQL_STATEMENT)
    _, note = gate.screen("req: " + SHAPE.removeprefix("shape: "))
    assert "output shape accepted" in note
    assert gate.screen(QUERY) == (QUERY, "")


def test_an_incomplete_shape_names_the_missing_facets_then_forces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = _gate(tmp_path, monkeypatch, SQL_STATEMENT)
    _, note = gate.screen("shape: the columns are id and name")
    assert "rows" in note
    assert "grouping" in note
    assert "1 of 3" in note
    refused, why = gate.screen(QUERY)
    assert refused is None
    assert "shape" in why
    assert "1 of 3" in why
    gate.screen("shape: columns again")
    _, last = gate.screen("shape: columns once more")
    assert "accepted anyway" in last
    assert gate.screen(QUERY) == (QUERY, "")
    assert session_log.read(gate.log)[-1]["req_incomplete"] is True


def test_algorithm_problems_keep_the_req_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = _gate(tmp_path, monkeypatch, MISSING_NUMBER)
    sent, note = gate.screen(QUERY)
    assert sent is None
    assert "req:" in note
    assert "shape" not in note
    assert gate.screen(SHAPE) == (SHAPE, "")
    assert _events(gate) == []


def test_an_unfetched_statement_defaults_to_the_stricter_req_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = _gate(tmp_path, monkeypatch, "reformat-department-table")
    _, note = gate.screen(QUERY)
    assert "req:" in note


def _sql_coach(tmp_path: Path) -> tuple[Any, str]:
    ask = FakeAsk([{"result": "Hi?"}] * 3, [{"result": json.dumps({"grade": "pass"})}])
    coach = make_coach(tmp_path, ask, fetch=lambda _s: ("Reformat", SQL_STATEMENT))
    return coach, started(coach)


def test_step_two_grades_the_shape_mechanically(tmp_path: Path) -> None:
    coach, sid = _sql_coach(tmp_path)
    grade(coach, sid, 1, answer="n is big")
    partial = grade(coach, sid, 2, answer="the columns are id and name")["data"]
    assert partial["grade"] == "partial"
    assert "one row per" in partial["feedback"]
    assert "group" in partial["feedback"]
    passed = grade(coach, sid, 2, answer=SHAPE)["data"]
    assert (passed["grade"], passed["next_step"]) == ("pass", 3)
    assert coach.session is not None
    assert coach.session.info()["kind"] == "sql"
    assert coach.deps.ask.prompts("haiku")  # step 1 only; step 2 asked no model
    assert len(coach.deps.ask.prompts("haiku")) == 1


def test_step_two_still_rejects_code_as_a_shape(tmp_path: Path) -> None:
    coach, sid = _sql_coach(tmp_path)
    grade(coach, sid, 1, answer="n is big")
    got = grade(coach, sid, 2, answer=QUERY)["data"]
    assert (got["grade"], got["feedback"]) == ("fail", grading.READS_AS_CODE)


def test_an_algorithm_session_reports_its_kind(tmp_path: Path) -> None:
    coach = make_coach(tmp_path, FakeAsk([{"result": "Hi?"}]))
    started(coach)
    assert coach.session is not None
    assert coach.session.info()["kind"] == "algorithm"
