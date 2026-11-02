"""Statement parsing edge cases on synthetic statements."""

from __future__ import annotations

import pytest

from sql_drills import _lc_problem as lp


def test_two_examples_and_two_input_tables_without_schema_blocks() -> None:
    text = """Return the result table ordered by id in ascending order.
Example 1:
Input:
A table:
+----+-------+
| id | score |
+----+-------+
| 1  | 2.5   |
+----+-------+
B table:
+----+------------+
| id | at         |
+----+------------+
| 1  | 2020-01-02 |
+----+------------+
Output:
+----+
| id |
+----+
| 1  |
+----+
Example 2:
Input:
A table:
+----+-------+
| id | score |
+----+-------+
| 7  | 3000000000 |
+----+-------+
B table:
+----+------------+
| id | at         |
+----+------------+
| 7  | x |
+----+------------+
Output:
+----+
| id |
+----+
| 7  |
+----+
"""
    problem = lp.parse_problem(text)
    assert problem.ordered
    assert len(problem.examples) == 2
    first = lp.schema_sql(problem, problem.examples[0], "mysql")
    assert "`id` INT" in first
    assert "`score` DECIMAL(20,6)" in first
    assert "`at` DATE" in first
    second = lp.schema_sql(problem, problem.examples[1], "mysql")
    assert "`score` BIGINT" in second
    assert "`at` VARCHAR(255)" in second


def test_unnamed_input_table_with_single_schema_uses_that_name() -> None:
    text = """Table: Only

+-------------+------+
| Column Name | Type |
+-------------+------+
| a           | int  |
+-------------+------+
Example 1:
Input:
+---+
| a |
+---+
| 1 |
+---+
Output:
+---+
| a |
+---+
| 1 |
+---+
"""
    problem = lp.parse_problem(text)
    assert list(problem.examples[0].inputs) == ["Only"]


def test_unnamed_input_table_is_skipped_and_example_dropped() -> None:
    text = """Example 1:
Input:
+---+
| a |
+---+
| 1 |
+---+
Output:
+---+
| a |
+---+
| 1 |
+---+
"""
    with pytest.raises(lp.NoExamplesError):
        lp.parse_problem(text)


def test_html_statement_is_accepted() -> None:
    html = (
        "<p>Table: <code>T</code></p><pre>+-------------+------+\n"
        "| Column Name | Type |\n+-------------+------+\n| a | int |\n"
        "+-------------+------+</pre><p><strong>Example 1:</strong></p>"
        "<pre><strong>Input:</strong> \nT table:\n+---+\n| a |\n+---+\n| 1 |\n+---+\n"
        "<strong>Output:</strong> \n+---+\n| a |\n+---+\n| 1 |\n+---+\n</pre>"
    )
    problem = lp.parse_problem(html)
    assert problem.examples[0].expected.rows == [["1"]]


def test_no_examples_is_an_error() -> None:
    with pytest.raises(lp.NoExamplesError, match="no examples"):
        lp.parse_problem("Write a query. Nothing parseable here.")


def test_example_without_output_table_is_dropped() -> None:
    text = """Example 1:
Input:
T table:
+---+
| a |
+---+
| 1 |
+---+
Output: n/a
Example 2:
Input: n = 5
Output: 3
"""
    with pytest.raises(lp.NoExamplesError):
        lp.parse_problem(text)


def test_order_detection_ignores_schema_blocks_and_any_order() -> None:
    base = "Return the result table in **any order**.\nExample 1:\n"
    sorted_by = "Return the result sorted by id.\nExample 1:\n"
    in_block = "```\nthe table is ordered by id\n```\n" + base
    assert not lp.is_ordered(base)
    assert lp.is_ordered(sorted_by)
    assert not lp.is_ordered(in_block)
    assert lp.is_ordered("in descending order\nExample 1:")
    assert lp.is_ordered("ORDER BY it\nExample 1:")


_ONE = """Input:
{name}table:
+---+
| a |
+---+
| 1 |
+---+
Output:
+---+
| a |
+---+
| 1 |
+---+
"""


def test_input_after_output_starts_a_new_example_and_extra_tables_are_ignored() -> None:
    extra = "+---+\n| z |\n+---+\n| 9 |\n+---+\n"
    text = _ONE.format(name="T ") + extra + _ONE.format(name="U ")
    problem = lp.parse_problem(text)
    assert [list(e.inputs) for e in problem.examples] == [["T"], ["U"]]
    assert problem.examples[0].expected.columns == ["a"]


def test_schema_block_without_a_table_line_is_ignored() -> None:
    header = "+-------------+------+\n| Column Name | Type |\n+-------------+------+\n"
    problem = lp.parse_problem(header + "| a | int |\n+---+\n" + _ONE.format(name="T "))
    assert problem.schemas == {}


def test_types_come_from_the_matching_schema_else_from_the_rows() -> None:
    text = """Table: A

+-------------+------+
| Column Name | Type |
+-------------+------+
| a           | float |
+-------------+------+
Table: B

+-------------+------+
| Column Name | Type |
+-------------+------+
| b           | int  |
+-------------+------+
Example 1:
Input:
b table:
+---+-----+-----+-----+
| b | dt  | n   | e   |
+---+-----+-----+-----+
| 1 | 2020-01-02 03:04:05 | null | 1   |
| 2 | 2020-01-02 03:04:05 | null | 2.5 |
+---+-----+-----+-----+
A table:
+---+
| a |
+---+
Output:
+---+
| b |
+---+
| 1 |
+---+
"""
    problem = lp.parse_problem(text)
    sql = lp.schema_sql(problem, problem.examples[0], "postgresql")
    assert '"dt" TIMESTAMP' in sql
    assert '"n" VARCHAR(255)' in sql
    assert '"e" DECIMAL(20,6)' in sql
    assert '"a" DOUBLE PRECISION' in sql
    assert sql.count("INSERT") == 1


def test_a_stray_table_outside_input_and_output_is_ignored() -> None:
    stray = "+---+\n| z |\n+---+\n| 9 |\n+---+\n"
    problem = lp.parse_problem(stray + _ONE.format(name="T "))
    assert len(problem.examples) == 1
