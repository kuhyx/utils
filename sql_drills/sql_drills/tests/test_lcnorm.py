"""LeetCode/HackerRank-style cell canonicalisation and row comparison."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from sql_drills import _lcnorm

if TYPE_CHECKING:
    from sql_drills._dialect import Dialect


@pytest.mark.parametrize(
    ("raw", "dialect", "want"),
    [
        ("null", "mysql", "NULL"),
        ("NULL", "postgresql", "NULL"),
        ("0.50", "mysql", "0.5"),
        ("1.0", "postgresql", "1"),
        ("-0.00", "mysql", "0"),
        ("1E+3", "mysql", "1000"),
        ("8000", "mysql", "8000"),
        ("NaN", "mysql", "NaN"),
        ("abc  ", "mysql", "abc"),
        ("  lead", "mysql", "  lead"),
        ("", "mysql", ""),
        ("true", "mysql", "1"),
        ("FALSE", "mysql", "0"),
        ("t", "postgresql", "1"),
        ("f", "postgresql", "0"),
        ("t", "mysql", "t"),
        ("2018-12-18", "postgresql", "2018-12-18"),
    ],
)
def test_canon(raw: str, dialect: Dialect, want: str) -> None:
    assert _lcnorm.canon(raw, dialect) == want


def test_ordered_compare_is_positional() -> None:
    got = _lcnorm.compare_results([["1"], ["2"]], [["2"], ["1"]], "mysql", ordered=True)
    assert not got.match
    assert got.cell_diff == [(0, 0, "1", "2"), (1, 0, "2", "1")]


def test_unordered_compare_ignores_row_order_and_number_format() -> None:
    got = _lcnorm.compare_results(
        [["1", "null"], ["2", "0.50"]],
        [["2", "0.5"], ["1", "NULL"]],
        "mysql",
        ordered=False,
    )
    assert got.match
    assert got.cell_diff == []


def test_unordered_mismatch_lists_missing_and_extra() -> None:
    got = _lcnorm.compare_results(
        [["1"], ["2"]], [["1"], ["3"]], "mysql", ordered=False
    )
    assert not got.match
    assert got.missing_rows == [["2"]]
    assert got.extra_rows == [["3"]]
    assert got.cell_diff == [(1, 0, "2", "3")]


def test_duplicate_rows_are_counted() -> None:
    got = _lcnorm.compare_results([["1"], ["1"]], [["1"]], "mysql", ordered=False)
    assert not got.match


def test_subset_passes_when_every_expected_row_is_present() -> None:
    got = _lcnorm.compare_results(
        [["1"]], [["2"], ["1"]], "mysql", ordered=False, subset=True
    )
    assert got.match
    assert got.extra_rows == []


def test_subset_fails_on_a_missing_row() -> None:
    got = _lcnorm.compare_results(
        [["1"], ["9"]], [["1"]], "mysql", ordered=False, subset=True
    )
    assert not got.match
    assert got.missing_rows == [["9"]]
    assert got.extra_rows == []
