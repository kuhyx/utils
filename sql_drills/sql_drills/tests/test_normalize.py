"""Judge-style normalisation and the cell-level diff."""

from __future__ import annotations

from sql_drills import _normalize as n


def test_parse_rows_splits_on_tabs() -> None:
    assert n.parse_rows("a\tb\nc\t\n") == [["a", "b"], ["c", ""]]
    assert n.parse_rows("") == []


def test_line_turns_tabs_into_spaces_and_rstrips() -> None:
    assert n.line(["a", "b  "]) == "a b"
    assert n.line(["a", ""]) == "a"
    assert n.line(["a", "", "b"]) == "a  b"


def test_clean_grid_strips_cells_and_trailing_blank_rows() -> None:
    grid = [[" a ", "b"], ["", " "], ["c", ""], ["", ""], [""]]
    assert n.clean_grid(grid) == [["a", "b"], ["", ""], ["c", ""]]


def test_clean_grid_all_blank_is_empty() -> None:
    assert n.clean_grid([[""], [" "]]) == []


def test_equal_outputs_match() -> None:
    cmp = n.compare([["a", "1"]], [["a", "1"]])
    assert cmp.match
    assert cmp.cell_diff == []
    assert cmp.extra_rows == cmp.missing_rows == []


def test_trailing_blank_cell_is_judge_equal() -> None:
    assert n.compare([["a"]], [["a", ""]]).match


def test_single_cell_difference_is_located() -> None:
    cmp = n.compare([["a", "1"], ["b", "2"]], [["a", "1"], ["b", "3"]])
    assert not cmp.match
    assert cmp.cell_diff == [(1, 1, "2", "3")]
    assert cmp.extra_rows == [["b", "3"]]
    assert cmp.missing_rows == [["b", "2"]]


def test_case_and_decimals_are_strict() -> None:
    assert not n.compare([["Ann"]], [["ann"]]).match
    assert not n.compare([["5.50"]], [["5.5"]]).match


def test_row_order_is_strict_but_not_extra_or_missing() -> None:
    cmp = n.compare([["a"], ["b"]], [["b"], ["a"]])
    assert not cmp.match
    assert cmp.cell_diff == [(0, 0, "a", "b"), (1, 0, "b", "a")]
    assert cmp.extra_rows == cmp.missing_rows == []


def test_extra_actual_row_gets_none_expected_cells() -> None:
    cmp = n.compare([["a"]], [["a"], ["z", "9"]])
    assert cmp.cell_diff == [(1, 0, None, "z"), (1, 1, None, "9")]
    assert cmp.extra_rows == [["z", "9"]]


def test_missing_actual_row_gets_none_actual_cells() -> None:
    cmp = n.compare([["a"], ["b"]], [["a"]])
    assert cmp.cell_diff == [(1, 0, "b", None)]
    assert cmp.missing_rows == [["b"]]


def test_wider_row_marks_the_extra_column() -> None:
    cmp = n.compare([["a"]], [["a", "x"]])
    assert not cmp.match
    assert cmp.cell_diff == [(0, 1, None, "x")]


def test_judge_line_rule_beats_cell_boundaries() -> None:
    # "a b" and "a<TAB>b" are the same line to an exact-match judge.
    cmp = n.compare([["a b"]], [["a", "b"]])
    assert cmp.match
    assert cmp.cell_diff == []


def test_trailing_blank_cells_do_not_show_in_the_diff() -> None:
    cmp = n.compare([["a", ""]], [["b"]])
    assert cmp.cell_diff == [(0, 0, "a", "b")]
