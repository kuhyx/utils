"""Statement text to a runnable spec, on real fetched LeetCode statements."""

from __future__ import annotations

from pathlib import Path

from sql_drills import _lc_problem as lp

STATEMENTS = Path(__file__).parent / "statements"


def _statement(slug: str) -> str:
    return (STATEMENTS / f"{slug}.txt").read_text()


def test_reformat_department_table_example() -> None:
    problem = lp.parse_problem(_statement("reformat-department-table"))
    assert problem.schemas["Department"] == [
        ("id", "int"),
        ("revenue", "int"),
        ("month", "varchar"),
    ]
    assert not problem.ordered
    (example,) = problem.examples
    dept = example.inputs["Department"]
    assert dept.columns == ["id", "revenue", "month"]
    assert dept.rows[0] == ["1", "8000", "Jan"]
    assert len(dept.rows) == 5
    assert example.expected.columns[:2] == ["id", "Jan_Revenue"]
    assert "..." in example.expected.columns
    assert example.expected.rows[1] == ["2", "9000", "null", "null", "...", "null"]


def test_monthly_transactions_example_and_ddl() -> None:
    problem = lp.parse_problem(_statement("monthly-transactions-i"))
    (example,) = problem.examples
    assert example.expected.columns[0] == "month"
    assert len(example.expected.rows) == 3
    my = lp.schema_sql(problem, example, "mysql")
    assert "CREATE TABLE `Transactions`" in my
    assert "`state` VARCHAR(255)" in my
    assert "`trans_date` DATE" in my
    assert "(121, " not in my  # values are quoted literals
    assert "('121', 'US', 'approved', '1000', '2018-12-18')" in my
    pg = lp.schema_sql(problem, example, "postgresql")
    assert 'CREATE TABLE "transactions"' in pg
    assert '"trans_date" DATE' in pg


def test_schema_nulls_and_quotes() -> None:
    text = """Table: T

+-------------+---------+
| Column Name | Type    |
+-------------+---------+
| id          | int     |
| name        | varchar |
+-------------+---------+

Example 1:

Input:
T table:
+----+------+
| id | name |
+----+------+
| 1  | null |
| 2  | it's |
+----+------+
Output:
+----+
| id |
+----+
| 2  |
+----+
"""
    problem = lp.parse_problem(text)
    sql = lp.schema_sql(problem, problem.examples[0], "mysql")
    assert "('1', NULL)" in sql
    assert "('2', 'it''s')" in sql
