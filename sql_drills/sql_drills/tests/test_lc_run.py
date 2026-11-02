"""``run_problem`` against stub sandboxes: no Docker, no network."""

from __future__ import annotations

from typing import TYPE_CHECKING

import sql_drills as sd
from sql_drills._sandbox import Executed
from sql_drills.tests.stubs import GOOD_ROWS, MONTHS, done, install, statement

if TYPE_CHECKING:
    import pytest


def test_elided_columns_compare_only_the_named_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schemas, boxes = install(monkeypatch, done(["id", *MONTHS], GOOD_ROWS))
    (res,) = sd.run_problem(statement("reformat-department-table"), "SELECT 1", "mysql")
    assert res.ok
    assert res.match, res.cell_diff
    assert res.note is not None
    assert "..." in res.note
    assert schemas[0] == "dialect=mysql"
    assert schemas[1].startswith("CREATE TABLE `Department`")
    assert boxes[0].sqls == ["SELECT 1"]
    assert res.columns == ["id", *MONTHS]


def test_postgres_lowercase_names_and_row_order_are_fine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cols = ["id", *[m.lower() for m in MONTHS]]
    install(monkeypatch, done(cols, list(reversed(GOOD_ROWS))))
    (res,) = sd.run_problem(
        statement("reformat-department-table"), "SELECT 1", "postgresql"
    )
    assert res.match


def test_wrong_value_gives_a_cell_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = [list(r) for r in GOOD_ROWS]
    bad[0][1] = "1"
    install(monkeypatch, done(["id", *MONTHS], bad))
    (res,) = sd.run_problem(statement("reformat-department-table"), "x", "mysql")
    assert not res.match
    assert res.cell_diff
    assert res.missing_rows
    assert res.extra_rows


def test_missing_named_column_does_not_match(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [r[:-1] for r in GOOD_ROWS]
    install(monkeypatch, done(["id", *MONTHS[:-1]], rows))
    (res,) = sd.run_problem(statement("reformat-department-table"), "x", "mysql")
    assert not res.match


def test_query_error_is_reported_per_example(monkeypatch: pytest.MonkeyPatch) -> None:
    err = Executed(
        ok=False, error='ERROR:  column "Jan" does not exist', code=None, rows=[]
    )
    install(monkeypatch, err)
    (res,) = sd.run_problem(statement("reformat-department-table"), "x", "postgresql")
    assert not res.ok
    assert not res.match
    assert res.error == 'ERROR:  column "Jan" does not exist'
    assert res.rows == []
    assert res.expected_rows[0][0] == "1"


def test_monthly_transactions_unordered_match(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        ["2019-01", "DE", "1", "1", "2000", "2000"],
        ["2018-12", "US", "2", "1", "3000.00", "1000"],
        ["2019-01", "US", "1", "1", "2000", "2000"],
    ]
    cols = ["month", "country", "trans_count", "approved_count", "a", "b"]
    install(monkeypatch, done(cols, rows))
    (res,) = sd.run_problem(statement("monthly-transactions-i"), "x", "mysql")
    assert res.match
    assert res.note is None


def test_ordered_statement_demands_order(monkeypatch: pytest.MonkeyPatch) -> None:
    text = statement("monthly-transactions-i").replace(
        "**any order**", "ordered by month"
    )
    rows = [
        ["2019-01", "DE", "1", "1", "2000", "2000"],
        ["2018-12", "US", "2", "1", "3000", "1000"],
        ["2019-01", "US", "1", "1", "2000", "2000"],
    ]
    install(monkeypatch, done(["a"] * 6, rows))
    (res,) = sd.run_problem(text, "x", "mysql")
    assert not res.match


def test_elided_rows_need_only_the_listed_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    text = """Example 1:
Input:
T table:
+---+
| a |
+---+
| 1 |
+---+
Output:
+-----+
| a   |
+-----+
| 2   |
| ... |
+-----+
"""
    install(monkeypatch, done(["a"], [["1"], ["2"], ["3"]]))
    (res,) = sd.run_problem(text, "x", "mysql")
    assert res.match
    assert res.note is not None
    assert "rows" in res.note
