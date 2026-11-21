"""The 14 skeleton sheets: one code template with holes per curriculum unit.

A sheet is printed verbatim inside a fenced block of a coach reply, so every
sheet is judged by the real no-solution detector (`gate_detector`) the way the
Stop hook would judge that reply.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

import pytest

import leetcode_coach
from leetcode_coach import gate_detector as det
from leetcode_coach import stop_gate

PKG = Path(leetcode_coach.__file__).resolve().parent
SHEETS = PKG / "skeletons"
RULES = PKG / "DOCS-skeletons.md"

# Copied from the guard's curriculum (leetcode_guard/curriculum.json, 2026-11-21)
# on purpose: the coach never reads the guard repo, not even at test time.
UNITS = (
    "scans",
    "hashing",
    "math",
    "bits",
    "sorting-greedy",
    "pointers-window",
    "prefix-sums",
    "stack-queue",
    "binary-search",
    "lists-recursion",
    "trees",
    "heap-dp",
    "sql",
    "js-pandas",
)
HOLE = "/* HOLE:"
MIN_HOLES = 3
MAX_LINES = 75
MAX_CHARS = 3600
TS_ONLY = re.compile(
    r":\s*(?:number|string|boolean|void|any)\b|<[A-Za-z]+[\w, \[\]]*>\(|"
    r"\binterface\b|\bas\s+(?:number|string|const)\b|\btype\s+\w+\s*="
)

# Names real LeetCode easy starters use: a sheet fence holding one would be
# bounced on that problem, so none may appear (whole word).
STARTER_WORDS = frozenset(
    re.findall(
        r"\w+",
        "nums nums1 nums2 target head root node list1 list2 l1 l2 prices arr "
        "array strs haystack needle matrix grid board digits height heights "
        "intervals words word text ransomNote magazine candies accounts sentence "
        "paragraph banned num numbers mat cost flowers stones coins people "
        "citations points customers orders salary employee scores sequence "
        "pattern low high count result data input items twoSum isValid maxProfit "
        "climbStairs mergeTwoLists isPalindrome removeDuplicates hammingWeight "
        "reverseBits singleNumber missingNumber majorityElement "
        "containsDuplicate isAnagram search searchInsert pivotIndex runningSum "
        "maxDepth invertTree inorderTraversal fib lengthOfLastWord plusOne "
        "addBinary mySqrt rob minCostClimbingStairs countBits isSubsequence "
        "longestCommonPrefix romanToInt",
    ),
)
# Easy "design" method names: a sheet may use them, but only as a verbatim quote.
DESIGN_WORDS = frozenset(
    re.findall(
        r"\w+",
        "push pop peek top empty add get put set has remove contains next ping "
        "getMin insert startsWith enqueue dequeue size key value",
    ),
)

Entry = dict[str, Any]


def _sheet(unit: str) -> str:
    return (SHEETS / f"DOCS-{unit}.md").read_text(encoding="utf-8")


def _fences(text: str) -> list[str]:
    return re.findall(r"```\n(.*?)```", text, re.DOTALL)


def _transcript(sheet: str, idents: str) -> list[Entry]:
    """A starter with `idents` as parameters, then a tool result holding the sheet."""
    starter = f"## Starter code\n```\nvar f = function({idents}) {{}};\n```"
    return [
        {"type": "user", "message": {"content": starter}},
        {
            "type": "user",
            "message": {"content": [{"type": "tool_result", "content": sheet}]},
        },
    ]


def test_the_unit_list_has_14_distinct_ids() -> None:
    assert len(UNITS) == len(set(UNITS)) == 14


def test_the_sheet_directory_holds_exactly_the_14_sheets() -> None:
    assert sorted(p.name for p in SHEETS.glob("*")) == sorted(
        f"DOCS-{u}.md" for u in UNITS
    )


@pytest.mark.parametrize("unit", UNITS)
def test_every_sheet_names_its_unit_and_ends_with_a_fence(unit: str) -> None:
    text = _sheet(unit)
    assert text.startswith("## Skeleton: ")
    assert f"({unit})" in text.splitlines()[0]
    assert text.rstrip().endswith("```")
    assert "Signal:" in text
    assert "Trap:" in text


@pytest.mark.parametrize("unit", UNITS)
def test_every_sheet_has_enough_holes(unit: str) -> None:
    need = 4 if unit == "js-pandas" else MIN_HOLES
    code = "\n".join(_fences(_sheet(unit)))
    assert code.count(HOLE) >= need
    assert all(line.count(HOLE) == line.count("*/") for line in code.splitlines())


@pytest.mark.parametrize("unit", UNITS)
def test_a_sheet_is_small_and_has_no_stray_backticks(unit: str) -> None:
    text = _sheet(unit)
    assert len(text.splitlines()) <= MAX_LINES
    assert len(text) <= MAX_CHARS
    fence_lines = [ln for ln in text.splitlines() if ln.startswith("```")]
    assert fence_lines
    assert all(ln == "```" for ln in fence_lines), (
        "bare fences: a language tag breaks quoting"
    )
    assert len(fence_lines) % 2 == 0
    assert text.count("`") == 3 * len(fence_lines)


@pytest.mark.parametrize("unit", UNITS)
def test_a_sheet_never_returns_an_answer_of_its_own(unit: str) -> None:
    for line in "\n".join(_fences(_sheet(unit))).splitlines():
        if re.search(r"\breturn\b", line):
            assert HOLE in line, line


@pytest.mark.parametrize("unit", UNITS)
def test_every_sheet_passes_the_detector_unquoted(unit: str) -> None:
    text = _sheet(unit)
    bad = det.offending_snippets(text, set(STARTER_WORDS), "")
    assert bad == []
    code = "\n".join(_fences(text))
    for word in STARTER_WORDS:
        assert not re.search(rf"\b{word}\b", code), word


@pytest.mark.parametrize("unit", UNITS)
def test_every_sheet_passes_the_detector_as_a_verbatim_quote(unit: str) -> None:
    sheet = _sheet(unit)
    idents = sorted(STARTER_WORDS | DESIGN_WORDS)
    entries = _transcript(sheet, ", ".join(idents))
    assert det.starter_identifiers(entries) >= DESIGN_WORDS
    allowed = det.allowed_text(entries)
    assert (
        det.offending_snippets(sheet, det.starter_identifiers(entries), allowed) == []
    )


def test_the_quote_exemption_is_real_and_a_filled_hole_loses_it() -> None:
    sheet = _sheet("stack-queue")
    entries = _transcript(sheet, "push, pop")
    idents = det.starter_identifiers(entries)
    allowed = det.allowed_text(entries)
    assert det.offending_snippets(sheet, idents, allowed) == []
    filled = sheet.replace(HOLE, "/* filled:", 1).replace(
        "```\n", "```\nlet cheat = 1;\n", 1
    )
    assert det.offending_snippets(filled, idents, allowed) != []
    assert det.offending_snippets(sheet, idents, "") != []


def test_the_sql_sheet_is_sql() -> None:
    code = "\n".join(_fences(_sheet("sql")))
    assert re.search(r"^SELECT\b", code, re.MULTILINE)
    assert re.search(r"^FROM\b", code, re.MULTILINE)
    assert re.search(r"\bGROUP BY\b", code)
    for js in ("const ", "let ", "function", "=>", "return", "{", "}"):
        assert js not in code


def test_the_js_pandas_sheet_has_javascript_and_pandas_and_no_typescript() -> None:
    fences = _fences(_sheet("js-pandas"))
    assert len(fences) == 2
    js, pandas = fences
    assert re.search(r"setTimeout|clearTimeout|Promise|=>", js)
    assert "frame" in pandas
    assert re.search(r"\.groupby|\.merge|\.query|\.loc|\.drop", pandas)
    assert not TS_ONLY.search("\n".join(fences))


@pytest.mark.parametrize("unit", [u for u in UNITS if u not in {"sql", "js-pandas"}])
def test_the_typescript_sheets_use_typescript_types(unit: str) -> None:
    assert re.search(r":\s*(?:number|string|boolean)", "\n".join(_fences(_sheet(unit))))


def test_the_rule_text_covers_when_how_and_the_cost() -> None:
    text = RULES.read_text(encoding="utf-8")
    assert "python3 -m leetcode_coach.review_cli skeleton-open <slug> <unit>" in text
    for needle in (
        "first code attempt",
        "only when",
        "H1",
        "sign-off",
        "verbatim",
        "latest",
    ):
        assert needle in text, needle


@pytest.mark.parametrize("unit", UNITS)
def test_the_real_stop_gate_lets_a_verbatim_sheet_through(unit: str) -> None:
    """End to end: kuhy has coded, the command output is in the transcript."""
    sheet = _sheet(unit)
    attempt = (
        "my try\n```js\nvar twoSum = function(nums, target) {\n  let a = 1;\n};\n```"
    )
    entries = [
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "text",
                        "text": f"Base directory for this skill: {stop_gate.SKILL_LINK}",
                    }
                ]
            },
        },
        *_transcript(sheet, "twoSum, nums, target, push, pop, get, set, key, value"),
    ]
    entries.insert(2, {"type": "user", "message": {"content": attempt}})
    raw = "\n".join(json.dumps(e) for e in entries)
    raw += f'\n"text":"Base directory for this skill: {stop_gate.SKILL_LINK}'
    assert stop_gate.verdict(raw, sheet) is None
