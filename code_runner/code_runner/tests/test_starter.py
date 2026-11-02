import pytest

from code_runner._model import RunnerError
from code_runner._starter import Entry, extract_starter, parse_starter

PY_CLASS = """class Solution:
    def twoSum(self, nums: list[int], target: int) -> list[int]:
"""
PY_COMMENTED = """# Definition for singly-linked list.
# class ListNode:
#     def __init__(self, val=0, next=None):
class Solution:
    def solve(self, grid: Dict[str, Tuple[int, int]], k: int = 3, *rest) -> int:
        pass
"""
PY_FUNC = "def add(a: int, b: int = 2) -> int:\n    pass\n"
JS_VAR = """/**
 * @param {number[]} nums
 */
var twoSum = function(nums, target) {

};"""
JS_FUNC = "function isPalindrome(x, y = 3) {\n}\n"
JS_ARROW = "const f = (a, b) => {\n}\n"
JS_CLASS = "class Solution {\n  constructor() {}\n  solve(nums, ...rest) {\n  }\n}\n"
TS_FUNC = "function twoSum(nums: number[], target: number): number[] {\n};"
TS_ARROW = "const f = (a: Map<string, number>, b?: number): number => {\n}\n"


@pytest.mark.parametrize(
    ("lang", "text", "want"),
    [
        ("python3", PY_CLASS, Entry("Solution", "twoSum", ("nums", "target"))),
        ("python3", PY_COMMENTED, Entry("Solution", "solve", ("grid", "k"))),
        ("python3", PY_FUNC, Entry(None, "add", ("a", "b"))),
        ("javascript", JS_VAR, Entry(None, "twoSum", ("nums", "target"))),
        ("javascript", JS_FUNC, Entry(None, "isPalindrome", ("x", "y"))),
        ("javascript", JS_ARROW, Entry(None, "f", ("a", "b"))),
        ("javascript", JS_CLASS, Entry("Solution", "solve", ("nums",))),
        ("typescript", TS_FUNC, Entry(None, "twoSum", ("nums", "target"))),
        ("typescript", TS_ARROW, Entry(None, "f", ("a", "b"))),
    ],
)
def test_parse_starter(lang: str, text: str, want: Entry) -> None:
    assert parse_starter(lang, text) == want


@pytest.mark.parametrize(
    ("lang", "text"),
    [
        ("python3", "x = 1\n"),
        ("python3", "class Solution:\n    pass\n"),
        ("javascript", "// nothing here\n"),
        ("javascript", "class Solution {\n  constructor() {}\n}\n"),
        ("typescript", ""),
    ],
)
def test_starter_without_entry_is_refused(lang: str, text: str) -> None:
    with pytest.raises(RunnerError, match="entry point"):
        parse_starter(lang, text)


def test_extract_starter_takes_the_fenced_block() -> None:
    statement = (
        "# 1. Two Sum (Easy)\n\nbody\n\n## Starter code (python3)\n```\n"
        + PY_CLASS
        + "```\n\n## Site hints\nnope\n"
    )
    assert extract_starter(statement) == PY_CLASS


def test_extract_starter_without_section_is_empty() -> None:
    assert extract_starter("# 1. Two Sum\n\nno starter\n") == ""


def test_extract_starter_unfenced_runs_to_next_section() -> None:
    text = "intro\n## Starter code (javascript)\nvar f = function(a) {};\n## Hints\nx\n"
    assert extract_starter(text) == "var f = function(a) {};\n"
