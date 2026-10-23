"""The statement's examples and function name, as run_code needs them."""

from __future__ import annotations

import logging

import pytest

from leetcode_coach.relay import examples
from leetcode_coach.relay.examples import Example
from leetcode_coach.tests._relay_statements import (
    MERGE_INTERVALS,
    MISSING_NUMBER,
    TWO_SUM,
)


def test_plain_bold_labels() -> None:
    name, found = examples.parse(MISSING_NUMBER)
    assert name == "missingNumber"
    assert found == [
        Example(1, ([3, 0, 1],), 2),
        Example(2, ([0, 1],), 2),
        Example(3, ([9, 6, 4, 2, 3, 5, 7, 0, 1],), 8),
    ]


def test_code_spans_and_several_arguments_in_order() -> None:
    name, found = examples.parse(TWO_SUM)
    assert name == "twoSum"
    assert found[0] == Example(1, ([2, 7, 11, 15], 9), [0, 1])
    assert len(found) == 3


def test_fenced_nested_arrays() -> None:
    name, found = examples.parse(MERGE_INTERVALS)
    assert name == "merge"
    assert found[1] == Example(2, ([[1, 4], [4, 5]],), [[1, 5]])


def test_strings_with_commas_and_literals() -> None:
    text = (
        '**Input:** s = "a,b", k = [1,[2,3]], flag = true, none = null\n'
        "**Output:** false\n"
        "function solve(s, k, flag, none) {}\n"
    )
    name, found = examples.parse(text)
    assert name == "solve"
    assert found == [Example(1, ("a,b", [1, [2, 3]], True, None), False)]


def test_escaped_quote_inside_a_string() -> None:
    text = '**Input:** s = "a\\",b"\n**Output:** "x"\n'
    assert examples.parse(text)[1] == [Example(1, ('a",b',), "x")]


@pytest.mark.parametrize(
    ("starter", "name"),
    [
        ("const best = (nums) => 0;", "best"),
        ("let best = function (nums) {};", "best"),
        ("function best(nums) {}", "best"),
        ("class Solution {}", None),
    ],
)
def test_function_name_shapes(starter: str, name: str | None) -> None:
    assert (
        examples.parse(f"## Starter code (javascript)\n```\n{starter}\n```\n")[0]
        == name
    )


def test_an_example_whose_value_is_not_json_is_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    text = (
        "**Input:** root = [1,null,2]\n**Output:** [1,2]\n"
        "**Input:** head = 1->2\n**Output:** 2\n"
        "**Input:** n = 3\n**Output:** nope\n"
        "**Input:** 3\n**Output:** 3\n"
    )
    with caplog.at_level(logging.WARNING):
        _, found = examples.parse(text)
    assert found == [Example(1, ([1, None, 2],), [1, 2])]
    assert "skipped" in caplog.text


def test_output_without_input_and_hint_section_are_ignored() -> None:
    text = (
        "**Output:** 4\n**Input:** n = 1\n**Output:** 1\n"
        "## Site hints (do NOT show to the user unasked)\n"
        "- **Input:** n = 9\n**Output:** 9\n"
    )
    assert examples.parse(text)[1] == [Example(1, (1,), 1)]


def test_nothing_to_find() -> None:
    assert examples.parse("") == (None, [])
