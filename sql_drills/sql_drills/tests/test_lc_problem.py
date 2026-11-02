"""Statement text to a runnable spec, on synthetic LeetCode-layout statements."""

from __future__ import annotations

from sql_drills import _lc_problem as lp
from sql_drills.tests.synthetic import ORDERS, PIVOT


def test_pivot_example() -> None:
    problem = lp.parse_problem(PIVOT)
    assert problem.schemas["Shipments"] == [
        ("id", "int"),
        ("weight", "int"),
        ("month", "varchar"),
    ]
    assert not problem.ordered
    (example,) = problem.examples
    dept = example.inputs["Shipments"]
    assert dept.columns == ["id", "weight", "month"]
    assert dept.rows[0] == ["1", "400", "Jan"]
    assert len(dept.rows) == 5
    assert example.expected.columns[:2] == ["id", "Jan_Weight"]
    assert "..." in example.expected.columns
    assert example.expected.rows[1] == ["2", "900", "null", "null", "...", "null"]


def test_orders_example_and_ddl() -> None:
    problem = lp.parse_problem(ORDERS)
    (example,) = problem.examples
    assert example.expected.columns[0] == "month"
    assert len(example.expected.rows) == 3
    my = lp.schema_sql(problem, example, "mysql")
    assert "CREATE TABLE `Orders`" in my
    assert "`status` VARCHAR(255)" in my
    assert "`placed_on` DATE" in my
    assert "(121, " not in my  # values are quoted literals
    assert "('121', 'North', 'shipped', '1000', '2018-12-18')" in my
    pg = lp.schema_sql(problem, example, "postgresql")
    assert 'CREATE TABLE "orders"' in pg
    assert '"placed_on" DATE' in pg


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
