"""run_code: kuhy's JavaScript against the statement's examples, under node.

The real node runs the behaviour tests (the permission model is the point and
a fake cannot prove it); a fake runner covers the failure branches.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Any

import pytest

from leetcode_coach.relay import runcode
from leetcode_coach.tests._relay_statements import MISSING_NUMBER, TWO_SUM

NODE = shutil.which("node") or "/usr/bin/node"
needs_node = pytest.mark.skipif(not shutil.which("node"), reason="node not on PATH")

RIGHT = """var missingNumber = function(nums) {
  let x = nums.length;
  for (let i = 0; i < nums.length; i++) x ^= i ^ nums[i];
  return x;
};"""


@needs_node
def test_a_correct_solution_passes_every_example() -> None:
    out = runcode.run(RIGHT, MISSING_NUMBER, node=NODE)
    assert out == {
        "examples": [
            {"n": 1, "ok": True, "got": "2", "expected": "2"},
            {"n": 2, "ok": True, "got": "2", "expected": "2"},
            {"n": 3, "ok": True, "got": "8", "expected": "8"},
        ],
        "error": None,
    }


@needs_node
def test_a_wrong_answer_is_got_versus_expected() -> None:
    out = runcode.run("var twoSum = (nums, t) => [1, 0];", TWO_SUM, node=NODE)
    first = out["examples"][0]
    assert first == {"n": 1, "ok": False, "got": "[1,0]", "expected": "[0,1]"}
    assert out["error"] is None


@needs_node
def test_console_output_does_not_corrupt_results() -> None:
    code = (
        "var missingNumber = function(nums) {\n"
        "  console.log('2'); console.error('noise'); process.stdout.write('8\\n');\n"
        "  return 0;\n};"
    )
    out = runcode.run(code, MISSING_NUMBER, node=NODE)
    assert [e["got"] for e in out["examples"]] == ["0", "0", "0"]


@needs_node
def test_undefined_result_is_shown_as_undefined() -> None:
    out = runcode.run(
        "var missingNumber = function(nums) {};", MISSING_NUMBER, node=NODE
    )
    assert out["examples"][0]["got"] == "undefined"
    assert out["examples"][0]["ok"] is False


@needs_node
def test_a_syntax_error_reports_syntax_and_no_examples() -> None:
    out = runcode.run("var missingNumber = function(nums) {", MISSING_NUMBER, node=NODE)
    assert out == {"examples": [], "error": "syntax"}


@needs_node
def test_a_thrown_error_shows_only_its_class_name() -> None:
    code = (
        "var missingNumber = function(nums) { throw new TypeError('secret detail'); };"
    )
    out = runcode.run(code, MISSING_NUMBER, node=NODE)
    assert out["examples"][0]["got"] == "error: TypeError"
    assert "secret" not in str(out)


@needs_node
def test_a_top_level_crash_marks_every_example() -> None:
    code = "null.x;\nvar missingNumber = function(nums) { return 2; };"
    out = runcode.run(code, MISSING_NUMBER, node=NODE)
    assert [e["got"] for e in out["examples"]] == ["error: TypeError"] * 3


@needs_node
def test_reading_outside_its_directory_is_denied() -> None:
    code = (
        "var missingNumber = function(nums) {\n"
        "  return process.mainModule.require('fs').readFileSync('/etc/passwd', 'utf8');\n};"
    )
    out = runcode.run(code, MISSING_NUMBER, node=NODE)
    assert out["examples"][0]["got"] == "error: Error"
    assert "root" not in str(out)


@needs_node
def test_a_missing_function_is_an_error_per_example() -> None:
    out = runcode.run("var other = () => 1;", MISSING_NUMBER, node=NODE)
    assert out["examples"][0]["got"] == "error: ReferenceError"


@needs_node
def test_an_infinite_loop_times_out() -> None:
    code = "var missingNumber = function(nums) { for (;;) {} };"
    out = runcode.run(code, MISSING_NUMBER, node=NODE, timeout_s=1.0)
    assert out == {"examples": [], "error": "timeout"}


@needs_node
def test_a_long_result_is_truncated() -> None:
    code = "var missingNumber = function(nums) { return 'x'.repeat(5000); };"
    got = runcode.run(code, MISSING_NUMBER, node=NODE)["examples"][0]["got"]
    assert len(got) == runcode.MAX_SHOWN + 3
    assert got.endswith("...")


def test_no_examples_is_reported_without_running() -> None:
    def never(*_a: Any, **_k: Any) -> subprocess.CompletedProcess[bytes]:
        raise AssertionError

    assert runcode.run("x", "no examples here", runner=never) == {
        "examples": [],
        "error": "no_examples",
    }


def test_no_function_name_is_no_examples() -> None:
    text = "**Input:** n = 1\n**Output:** 1\n"
    assert runcode.run("x", text)["error"] == "no_examples"


def test_node_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.setenv("LEETCODE_NODE_BIN", str(tmp_path / "no-node"))
    assert runcode.run(RIGHT, MISSING_NUMBER) == {
        "examples": [],
        "error": "node_missing",
    }


def test_node_from_path_then_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LEETCODE_NODE_BIN", raising=False)
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    assert runcode.node_bin() == "/usr/bin/node"
    monkeypatch.setattr(shutil, "which", lambda _name: "/opt/node")
    assert runcode.node_bin() == "/opt/node"


def test_the_argv_is_fixed_and_the_env_minimal() -> None:
    seen: dict[str, Any] = {}

    def fake(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        seen.update(argv=argv, **kwargs)
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    runcode.run(RIGHT, MISSING_NUMBER, node="/n", runner=fake)
    tmp = seen["cwd"]
    assert seen["argv"] == [
        "/n",
        "--permission",
        f"--allow-fs-read={tmp}",
        "--max-old-space-size=128",
        f"{tmp}/run.js",
    ]
    assert seen["env"] == {"PATH": "/usr/bin:/bin"}
    assert seen["stdin"] is subprocess.DEVNULL
    assert "shell" not in seen


def _marked(stdout_for_token: Any) -> Any:
    def fake(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        script = kwargs["cwd"] + "/run.js"
        with open(script, encoding="utf-8") as fh:
            token = fh.read().split('const __mark = "', 1)[1].split('"', 1)[0]
        return subprocess.CompletedProcess(
            argv, 0, stdout_for_token(token).encode(), b""
        )

    return fake


def test_output_past_the_cap_is_dropped() -> None:
    def big(token: str) -> str:
        return f"{token} 1 ok 2\n" + "y" * runcode.MAX_OUTPUT + f"\n{token} 2 ok 2\n"

    out = runcode.run(RIGHT, MISSING_NUMBER, runner=_marked(big))
    assert [e["got"] for e in out["examples"]] == ["2", "no result", "no result"]


def test_forged_and_malformed_lines_are_ignored() -> None:
    def odd(token: str) -> str:
        return f"fake 1 ok 9\n{token} x ok 1\n{token} 1 ok {{bad\n{token} 2\n"

    out = runcode.run(RIGHT, MISSING_NUMBER, runner=_marked(odd))
    assert [e["got"] for e in out["examples"]] == ["{bad", "no result", "no result"]
    assert out["examples"][0]["ok"] is False
