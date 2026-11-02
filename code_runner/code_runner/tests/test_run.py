"""End to end through the real sandbox: every language, every kind of outcome."""

from __future__ import annotations

import pytest

from code_runner import CaseResult, Example, Limits, RunnerError, run
from code_runner.tests.conftest import (
    TWO_SUM_CODE,
    TWO_SUM_STARTER,
    needs_node,
    needs_sandbox,
)

LANGS = [
    pytest.param("python3", marks=needs_sandbox),
    pytest.param("javascript", marks=needs_node),
    pytest.param("typescript", marks=needs_node),
]
FAST = Limits(timeout_s=1.0)


def _two_sum(lang: str, code: str | None, examples: list[Example]) -> list[CaseResult]:
    return run(lang, code or TWO_SUM_CODE[lang], TWO_SUM_STARTER[lang], examples)


@pytest.mark.parametrize("lang", LANGS)
def test_correct_solution_passes_every_example(
    lang: str, two_sum_examples: list[Example]
) -> None:
    results = _two_sum(lang, None, two_sum_examples)
    assert [r.ok for r in results] == [True, True, True]
    assert [r.n for r in results] == [1, 2, 3]
    first = results[0]
    assert first.input == {"nums": [2, 7, 11, 15], "target": 9}
    assert first.expected == [0, 1]
    assert sorted(first.actual) == [0, 1]  # any order: [1, 0] is fine
    assert first.error is None
    assert first.ms >= 0


WRONG = {
    "python3": "class Solution:\n    def twoSum(self, nums, target):\n        return [0, 0]\n",
    "javascript": "var twoSum = function(nums, target) { return [0, 0]; };",
    "typescript": "function twoSum(nums: number[], target: number): number[] { return [0, 0]; }",
}


@pytest.mark.parametrize("lang", LANGS)
def test_wrong_answer_is_reported_with_actual_value(
    lang: str, two_sum_examples: list[Example]
) -> None:
    results = _two_sum(lang, WRONG[lang], two_sum_examples)
    assert [r.ok for r in results] == [False, False, False]
    assert results[0].actual == [0, 0]
    assert results[0].error is None


THROWS = {
    "python3": "class Solution:\n    def twoSum(self, nums, target):\n        return nums[99]\n",
    "javascript": "var twoSum = function(nums, target) { throw new RangeError('boom'); };",
    "typescript": "function twoSum(nums: number[], target: number): number[] { throw new RangeError('boom'); }",
}


@pytest.mark.parametrize("lang", LANGS)
def test_exception_becomes_an_error_per_case(
    lang: str, two_sum_examples: list[Example]
) -> None:
    results = _two_sum(lang, THROWS[lang], two_sum_examples[:1])
    only = results[0]
    assert only.ok is False
    assert only.actual is None
    assert only.error is not None
    assert only.error.split(":")[0] in {"IndexError", "RangeError"}


BROKEN = {
    "python3": "class Solution:\n    def twoSum(self, nums, target) return 1\n",
    "javascript": "var twoSum = function(nums, target) { return ; ;; }}",
    "typescript": "function twoSum(nums: number[], target: number): number[] { return [ }",
}


@pytest.mark.parametrize("lang", LANGS)
def test_syntax_error_is_reported(lang: str, two_sum_examples: list[Example]) -> None:
    results = _two_sum(lang, BROKEN[lang], two_sum_examples[:2])
    assert [r.ok for r in results] == [False, False]
    assert all(r.error and r.error.startswith("SyntaxError") for r in results)


PRINTS = {
    "python3": "class Solution:\n    def twoSum(self, nums, target):\n        print('hi', target)\n        return [0, 1]\n",
    "javascript": "var twoSum = function(nums, target) { console.log('hi', target); return [0, 1]; };",
    "typescript": "function twoSum(nums: number[], target: number): number[] { console.log('hi', target); return [0, 1]; }",
}


@pytest.mark.parametrize("lang", LANGS)
def test_prints_land_in_stdout_per_case(
    lang: str, two_sum_examples: list[Example]
) -> None:
    results = _two_sum(lang, PRINTS[lang], two_sum_examples[:2])
    assert results[0].stdout.strip() == "hi 9"
    assert results[1].stdout.strip() == "hi 6"


@pytest.mark.parametrize("lang", LANGS)
def test_missing_entry_point_in_code_is_a_case_error(
    lang: str, two_sum_examples: list[Example]
) -> None:
    code = {
        "python3": "x = 1\n",
        "javascript": "var other = 1;",
        "typescript": "const other = 1;",
    }
    results = _two_sum(lang, code[lang], two_sum_examples[:1])
    assert results[0].ok is False
    assert results[0].error is not None
    assert "twoSum" in results[0].error or "Solution" in results[0].error


def test_class_style_javascript_and_function_style_python() -> None:
    js = run(
        "javascript",
        "class Solution { solve(a, b) { return a + b; } }",
        "class Solution {\n  solve(a, b) {\n  }\n}",
        [Example(1, {"a": 1, "b": 2}, 3)],
    )
    py = run(
        "python3",
        "def add(a, b):\n    return a + b\n",
        "def add(a: int, b: int) -> int:\n",
        [Example(1, {"a": 1, "b": 2}, 3)],
    )
    assert js[0].ok is True
    assert py[0].ok is True


def test_python_prelude_and_aliases() -> None:
    code = "class Solution:\n    def f(self, xs: List[int]) -> int:\n        return collections.Counter(xs)[1]\n"
    starter = "class Solution:\n    def f(self, xs: List[int]) -> int:\n"
    out = run("python", code, starter, [Example(1, {"xs": [1, 1, 2]}, 2)])
    assert out[0].ok is True


def test_positional_fallback_when_statement_names_differ() -> None:
    out = run(
        "python3",
        "def add(a, b):\n    return a - b\n",
        "def add(a, b):\n",
        [Example(1, {"x": 5, "y": 2}, 3)],
    )
    assert out[0].ok is True


def test_argument_count_mismatch_is_a_case_error_without_running() -> None:
    out = run(
        "python3",
        "def add(a, b):\n    return a\n",
        "def add(a, b):\n",
        [Example(1, {"only": 5}, 3)],
    )
    assert out[0].ok is False
    assert out[0].error is not None
    assert out[0].error.startswith("ArgumentError")


def test_non_json_result_is_a_case_error() -> None:
    out = run(
        "python3",
        "def f(a):\n    return {1, 2}\n",
        "def f(a):\n",
        [Example(1, {"a": 1}, [1, 2])],
    )
    assert out[0].error is not None
    assert out[0].error.startswith("TypeError")


def test_deep_order_and_float_tolerance() -> None:
    out = run(
        "python3",
        "def f(a):\n    return [[2, 1], [0, -1]]\n",
        "def f(a):\n",
        [Example(1, {"a": 0}, [[-1, 0], [1, 2]], "deep")],
    )
    assert out[0].ok is True


def test_timeout_is_per_case() -> None:
    out = run(
        "python3",
        "def f(a):\n    while a:\n        pass\n    return 1\n",
        "def f(a):\n",
        [Example(1, {"a": 1}, 1), Example(2, {"a": 0}, 1)],
        limits=FAST,
    )
    assert out[0].error == "TimeLimitExceeded"
    assert out[0].ok is False
    assert out[0].ms >= 900
    assert out[1].ok is True


def test_unsupported_language_and_empty_examples() -> None:
    with pytest.raises(RunnerError, match="language"):
        run("cobol", "", "", [])
    assert run("python3", "def f(a): pass\n", "def f(a):\n", []) == []
