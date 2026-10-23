"""Tests for the LeetCode statement fetcher (public GraphQL, no login)."""

from __future__ import annotations

import io
import json
import runpy
from typing import Any, Self
import urllib.error
import urllib.request

import pytest

from leetcode_coach import fetch_problem

QUESTION = {
    "questionFrontendId": "1",
    "title": "Two Sum",
    "difficulty": "Easy",
    "content": (
        "<p>Given <code>nums</code>, return <strong>indices</strong> "
        "<em>exactly</em> once.</p><ul><li>one</li></ul><br>"
        "<div><span>x</span></div><pre>Input: [2,7]\n  Output: [0,1]</pre><b>b</b><i>i</i>"
    ),
    "isPaidOnly": False,
    "codeSnippets": [
        {"langSlug": "python3", "code": "class Solution:\n    pass\n"},
        {"langSlug": "javascript", "code": "var twoSum = function(nums) {};"},
    ],
    "topicTags": [{"name": "Array"}, {"name": "Hash Table"}],
    "hints": ["Use a map."],
}


@pytest.mark.parametrize(
    ("arg", "slug"),
    [
        ("https://leetcode.com/problems/two-sum/description/?x=1", "two-sum"),
        ("leetcode.cn/problems/add-two-numbers/submissions/1/", "add-two-numbers"),
        ("two-sum", "two-sum"),
    ],
)
def test_slug_from_urls_and_bare_slugs(arg: str, slug: str) -> None:
    assert fetch_problem.slug_from(arg) == slug


def test_slug_from_rejects_anything_else() -> None:
    with pytest.raises(ValueError, match="not a LeetCode problem URL or slug"):
        fetch_problem.slug_from("Two Sum!")


def test_render_markdown_with_starter_and_hidden_hints() -> None:
    out = fetch_problem.render(QUESTION, "javascript")
    assert out.startswith("# 1. Two Sum (Easy)\nTags: Array, Hash Table\n")
    assert "Languages available: python3, javascript" in out
    assert "Given `nums`, return **indices** _exactly_ once." in out
    assert "\n- one" in out
    assert "```\nInput: [2,7]\n  Output: [0,1]\n```" in out
    assert "**b**_i_" in out
    assert "## Starter code (javascript)\n```\nvar twoSum" in out
    assert out.endswith("## Site hints (do NOT show to the user unasked)\n- Use a map.")


def test_render_falls_back_to_the_first_language_and_no_extras() -> None:
    bare = {**QUESTION, "content": None, "topicTags": [], "hints": []}
    out = fetch_problem.render(bare, "rust")
    assert "Tags: none" in out
    assert "## Starter code (python3)" in out
    assert "Site hints" not in out
    empty = {**bare, "codeSnippets": []}
    out = fetch_problem.render(empty, "rust")
    assert "Languages available: none" in out
    assert "Starter code" not in out


class FakeResponse(io.BytesIO):
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def test_fetch_posts_the_query(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Any] = []

    def urlopen(req: Any, timeout: int) -> FakeResponse:
        seen.append((req.full_url, json.loads(req.data), req.get_header("Referer")))
        return FakeResponse(json.dumps({"data": {"question": QUESTION}}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert fetch_problem.fetch("two-sum") == QUESTION
    url, body, referer = seen[0]
    assert url == "https://leetcode.com/graphql"
    assert body["variables"] == {"s": "two-sum"}
    assert referer == "https://leetcode.com/problems/two-sum/"


def _main(monkeypatch: pytest.MonkeyPatch, argv: list[str], fetched: Any) -> int:
    def fetch(_slug: str) -> Any:
        if isinstance(fetched, Exception):
            raise fetched
        return fetched

    monkeypatch.setattr("sys.argv", ["fetch_problem.py", *argv])
    monkeypatch.setattr(fetch_problem, "fetch", fetch)
    return fetch_problem.main()


def test_main_prints_the_problem(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(monkeypatch, ["two-sum", "--lang", "python3"], QUESTION) == 0
    out = capsys.readouterr().out
    assert out.startswith("# 1. Two Sum (Easy)\n")
    assert "## Starter code (python3)" in out


@pytest.mark.parametrize(
    ("fetched", "code", "err"),
    [
        (urllib.error.URLError("offline"), 1, "fetch failed: <urlopen error offline>"),
        (None, 2, "problem 'two-sum' is unknown or premium-only"),
        ({**QUESTION, "isPaidOnly": True}, 2, "premium-only"),
        ({**QUESTION, "content": ""}, 2, "premium-only"),
    ],
)
def test_main_failures_exit_with_a_reason(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fetched: Any,
    code: int,
    err: str,
) -> None:
    assert _main(monkeypatch, ["two-sum"], fetched) == code
    captured = capsys.readouterr()
    assert captured.out == ""
    assert err in captured.err


def test_main_rejects_a_bad_argument(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(monkeypatch, ["Not A Slug"], QUESTION) == 1
    assert capsys.readouterr().err.startswith("fetch failed: not a LeetCode problem")


def test_script_entry_point(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["fetch_problem.py", "Bad Slug"])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(fetch_problem.__file__, run_name="__main__")
    assert exit_info.value.code == 1
    assert "fetch failed" in capsys.readouterr().err
