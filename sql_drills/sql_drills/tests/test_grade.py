"""``run`` and ``check_prediction`` against builtin drills and a fake MySQL."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

import sql_drills as sd
from sql_drills import _engine, _paths

if TYPE_CHECKING:
    from sql_drills._dialect import Dialect
    from sql_drills.tests.conftest import FakeMysql, FakePsql

_PIVOT = "01_pivot_sum"
_PIVOT_ROWS = [
    ["East", "0", "300", "0", "25"],
    ["North", "200", "150", "0", "200"],
    ["South", "90", "0", "100", "0"],
    ["West", "10", "0", "0", "0"],
]
_HEADER = "region\tQ1\tQ2\tQ3\tQ4"


def _tsv(rows: list[list[str]]) -> str:
    return "".join("\t".join(r) + "\n" for r in rows)


def test_fixture_expected_is_tab_separated() -> None:
    text = (_paths.builtin_dir() / _PIVOT / "expected.txt").read_text()
    assert text == _tsv(_PIVOT_ROWS)


def test_run_match(fake_mysql: FakeMysql) -> None:
    fake_mysql.say("my query", stdout=_tsv(_PIVOT_ROWS), header=_HEADER)
    res = sd.run(_PIVOT, "my query")
    assert res.ok
    assert res.match
    assert res.error is None
    assert res.columns == ["region", "Q1", "Q2", "Q3", "Q4"]
    assert res.rows == res.expected_rows == _PIVOT_ROWS
    assert res.cell_diff == []


def test_run_builds_the_drill_schema_first(fake_mysql: FakeMysql) -> None:
    sd.run(_PIVOT, "my query")
    assert fake_mysql.calls[1]["sql"] == sd.get_drill(_PIVOT).schema_sql
    assert str(fake_mysql.calls[-2]["sql"]).endswith("my query")
    assert "DROP DATABASE" in str(fake_mysql.calls[-1]["sql"])


def test_run_wrong_cell_is_located(fake_mysql: FakeMysql) -> None:
    wrong = [list(r) for r in _PIVOT_ROWS]
    wrong[1][2] = "151"
    fake_mysql.say("my query", stdout=_tsv(wrong), header=_HEADER)
    res = sd.run(_PIVOT, "my query")
    assert res.ok
    assert not res.match
    assert res.cell_diff == [(1, 2, "150", "151")]
    assert res.extra_rows == [wrong[1]]
    assert res.missing_rows == [_PIVOT_ROWS[1]]


def test_run_sql_error_is_visible(fake_mysql: FakeMysql) -> None:
    fake_mysql.say("my query", stderr="ERROR 1064 (42000): syntax", rc=1)
    res = sd.run(_PIVOT, "my query")
    assert not res.ok
    assert not res.match
    assert res.error == "ERROR 1064 (42000): syntax"
    assert res.rows == []
    assert res.expected_rows == _PIVOT_ROWS


def test_run_on_error_drill_matches_by_error_code(fake_mysql: FakeMysql) -> None:
    fake_mysql.say("bad", stderr="ERROR 1054 (42S22): Unknown column", rc=1)
    res = sd.run("t06_alias_in_where", "bad")
    assert not res.ok
    assert res.match
    assert res.rows == res.expected_rows == [["ERROR 1054"]]


def test_run_on_error_drill_with_other_error_code(fake_mysql: FakeMysql) -> None:
    fake_mysql.say("bad", stderr="ERROR 1146 (42S02): no table", rc=1)
    res = sd.run("t06_alias_in_where", "bad")
    assert not res.match
    assert res.cell_diff == [(0, 0, "ERROR 1054", "ERROR 1146")]


def test_run_on_error_drill_with_codeless_failure(fake_mysql: FakeMysql) -> None:
    fake_mysql.say("bad", stderr="gone", rc=1)
    res = sd.run("t06_alias_in_where", "bad")
    assert not res.match
    assert res.rows == []


def test_run_unknown_drill() -> None:
    with pytest.raises(sd.UnknownDrillError):
        sd.run("nope", "SELECT 1")


def test_run_engine_failure_propagates(fake_mysql: FakeMysql) -> None:
    fake_mysql.say("CREATE DATABASE", stderr="Cannot connect", rc=1)
    with pytest.raises(_engine.EngineError):
        sd.run(_PIVOT, "SELECT 1")


def test_prediction_match_needs_no_engine(fake_mysql: FakeMysql) -> None:
    res = sd.check_prediction("t01_null_not_equal", [["Bob"], ["", ""]])
    assert res.match
    assert res.cell_diff == []
    assert res.actual_rows == [["Bob"]]
    assert res.error is None
    assert fake_mysql.calls == []


def test_prediction_mismatch_is_located() -> None:
    res = sd.check_prediction("t01_null_not_equal", [["Ann"], ["Bob"]])
    assert not res.match
    assert res.cell_diff == [(0, 0, "Bob", "Ann"), (1, 0, None, "Bob")]
    assert res.actual_rows == [["Bob"]]
    assert res.extra_rows == [["Ann"]]
    assert res.missing_rows == []


def test_prediction_is_case_strict() -> None:
    res = sd.check_prediction("t05_anti_join", [["Cid"], ["Dee"]])
    assert res.match
    assert not sd.check_prediction("t05_anti_join", [["Cid"], ["dee"]]).match


@pytest.mark.parametrize("typed", ["ERROR", "error", " Error ", "ERROR 1054"])
def test_error_prediction_accepts_error_with_or_without_code(typed: str) -> None:
    res = sd.check_prediction("t06_alias_in_where", [[typed]])
    assert res.match
    assert res.actual_rows == [["ERROR 1054"]]
    assert res.error is not None
    assert "total" in res.error


def test_wrong_error_code_or_rows_do_not_match() -> None:
    assert not sd.check_prediction("t06_alias_in_where", [["ERROR 1146"]]).match
    assert not sd.check_prediction("t06_alias_in_where", [["1", "50"]]).match


def test_error_word_is_only_special_on_error_drills() -> None:
    assert not sd.check_prediction("t01_null_not_equal", [["ERROR"]]).match


def test_prediction_on_write_drill_is_refused() -> None:
    with pytest.raises(sd.DrillKindError, match="write"):
        sd.check_prediction(_PIVOT, [["x"]])


def test_run_rejects_unknown_dialect() -> None:
    with pytest.raises(sd.DialectError):
        sd.run(_PIVOT, "x", dialect=cast("Dialect", "oracle"))


def test_run_on_postgres_translates_schema_and_compares_leetcode_style(
    fake_pg: FakePsql,
) -> None:
    fake_pg.say("my query", stdout="region,Q1\nEast,0.0\n")
    res = sd.run("01_pivot_sum", "my query", dialect="postgresql")
    assert res.ok
    assert res.columns == ["region", "Q1"]
    assert res.rows == [["East", "0.0"]]
    assert not res.match
    assert res.cell_diff
    assert "`" not in str(fake_pg.calls[1]["commands"])


def test_run_on_postgres_reports_the_engine_error_text(fake_pg: FakePsql) -> None:
    fake_pg.say("bad", stderr="ERROR:  nope", rc=3)
    res = sd.run("01_pivot_sum", "bad", dialect="postgresql")
    assert (res.ok, res.match, res.error) == (False, False, "ERROR:  nope")
    assert res.rows == []


def test_run_on_postgres_matches_equal_numbers(fake_pg: FakePsql) -> None:
    rows = "".join(",".join(r) + "\n" for r in _PIVOT_ROWS)
    fake_pg.say("my query", stdout="region,q1,q2,q3,q4\n" + rows.replace("0,", "0.00,"))
    assert sd.run(_PIVOT, "my query", dialect="postgresql").match
