"""Tests for the transcript parsing and snippet detection behind the Stop gate."""

from __future__ import annotations

from typing import Any

from leetcode_coach import gate_detector as det


def _user(content: object) -> dict[str, Any]:
    return {"type": "user", "message": {"content": content}}


def test_transcript_lines_skips_garbage_and_non_objects() -> None:
    raw = '{"a": 1}\nnot json\n[1, 2]\n{"b": 2}\n'
    assert det.transcript_lines(raw) == [{"a": 1}, {"b": 2}]


def test_text_of_joins_text_and_tool_results() -> None:
    msg = _user(
        [
            {"type": "text", "text": "hi"},
            {"type": "tool_result", "content": "plain"},
            {"type": "tool_result", "content": [{"text": "a"}, {"text": "b"}]},
            {"type": "image"},
        ]
    )
    assert det.text_of(msg) == "hi\nplain\na b"
    assert det.text_of(_user("s")) == "s"
    assert det.text_of({}) == ""


def test_kuhy_text_drops_skill_body_hook_echo_and_tool_results() -> None:
    msg = _user(
        [
            {"type": "text", "text": "mine"},
            {"type": "text", "text": "Base directory for this skill: /x"},
            {"type": "text", "text": "Stop hook feedback: `fn(...args)`"},
            {"type": "tool_result", "content": "fetched"},
        ]
    )
    assert det.kuhy_text(msg) == "mine"
    assert det.kuhy_text(_user("typed")) == "typed"


def test_starter_identifiers_from_js_and_python_starters() -> None:
    js = _user(
        "## Starter code (javascript)\n```\n/**\n * @param {number[]} nums\n"
        " * log(...argsArr)\n */\nvar twoSum = function(nums, target) {\n};\n```"
    )
    assert det.starter_identifiers([js]) == {"twoSum", "nums", "target"}
    py = _user(
        "## Starter code (python3)\n```\nclass Solution:\n"
        "    def maxArea(self, height: List[int], *rest, k=3) -> int:\n```"
    )
    assert det.starter_identifiers([py]) == {"maxArea", "height", "rest"}
    unfenced = _user("## Starter code\nfunction sortPeople(names, heights) {")
    assert det.starter_identifiers([unfenced]) == {"sortPeople", "names", "heights"}
    no_params = _user("## Starter code\n```\nfunction makeCounter() {}\n```")
    assert det.starter_identifiers([no_params]) == {"makeCounter"}


def test_starter_identifiers_ignores_other_entries() -> None:
    assistant = {"type": "assistant", "message": {"content": "## Starter code\nf(ab)"}}
    assert det.starter_identifiers([assistant, _user("no starter")]) == set()
    assert det.starter_identifiers([_user("## Starter code\n```\nfn = (a)\n```")]) == {
        "fn"
    }


def test_allowed_text_covers_kuhy_and_fetched_problem() -> None:
    entries = [
        _user([{"type": "text", "text": "my  code\n x"}]),
        _user([{"type": "tool_result", "content": "statement"}]),
        {"type": "assistant", "message": {"content": "never"}},
        _user("plain"),
    ]
    assert det.allowed_text(entries) == "my code x statement plain"


def test_offending_snippets_rules() -> None:
    idents = {"nums", "args"}
    reply = (
        "`nums.push(1)` and `nums` and `x = 1` and\n"
        "```js\nconst s = new Set(nums)\n```\n"
        "```javascript```\n"
        "`fn(...args)` vs `fn(...argsArr)` and `" + "nums[0] = " + "1" * 90 + "`"
    )
    bad = det.offending_snippets(reply, idents, "fn(...argsArr)")
    assert bad == [
        "nums.push(1)",
        "const s = new Set(nums)",
        "fn(...args)",
        ("nums[0] = " + "1" * 90)[:80],
    ]
    assert det.offending_snippets("`nums.push(1)`", idents, "x nums.push(1) y") == []
    assert det.offending_snippets("`f(...)`", {"f"}, "") == ["f(...)"]
