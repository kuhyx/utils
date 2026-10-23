"""Tests for the REPL's req-before-code phase gate and the rung marker."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from leetcode_coach import (
    local_prompt,
    local_session,
    phase,
    req_check,
    session_log,
    toolbox,
)

if TYPE_CHECKING:
    from pathlib import Path

CODE = "function missingNumber(nums) {\n  return 0;\n}"


@pytest.mark.parametrize(
    ("block", "verdict"),
    [
        ("```js\nlet x = 1\n```", True),
        (CODE, True),
        ("return acc;", True),
        ("const seen = new Set()", True),
        ("nums.map(x => x * 2)", True),
        ("def f(nums):", True),
        ("for (let i = 0; i < n; i++)", True),
        ("is it XOR?", False),
        ("I think (not sure) it is about pairs", False),
        ("req: a = b", False),
        ("is it x ^ y?", None),
        ("a = b", None),
        ("what does f(3) give", None),
    ],
)
def test_regex_verdict(block: str, verdict: bool | None) -> None:
    assert phase.regex_verdict(block) is verdict


@pytest.mark.parametrize(
    ("text", "clean", "rung"),
    [
        ("What next?\n\n<!-- rung:H1 -->\n", "What next?", "H1"),
        ("A <!-- rung:H0 -->B?<!--rung: H3-->", "A B?", "H3"),
        ("No marker?", "No marker?", None),
        ("Bad <!-- rung:H7 -->?", "Bad <!-- rung:H7 -->?", None),
    ],
)
def test_split_rung(text: str, clean: str, rung: str | None) -> None:
    assert local_prompt.split_rung(text) == (clean, rung)


def _verdicts(*verdicts: str) -> list[dict[str, object]]:
    return [{"event": "req_check", "verdict": v} for v in verdicts]


def test_req_state() -> None:
    assert phase.req_state([]) == phase.ReqState(accepted=False, forced=False, tries=0)
    assert phase.req_state(_verdicts("incomplete", "pass")).accepted
    assert phase.req_state(_verdicts("unverified")).accepted
    forced = phase.req_state(_verdicts("incomplete", "incomplete", "incomplete"))
    assert forced == phase.ReqState(accepted=False, forced=True, tries=3)
    assert forced.open


class _Checks:
    """Scripted `req_check.check` results; counts statement fetches."""

    def __init__(self, *results: req_check.Check) -> None:
        self.results = list(results)
        self.statements: list[str] = []

    def __call__(
        self, statement: str, _req: str, _box: object, _ask: object = None
    ) -> req_check.Check:
        self.statements.append(statement)
        return self.results.pop(0)


def _gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *results: req_check.Check
) -> tuple[phase.PhaseGate, _Checks]:
    checks = _Checks(*results)
    monkeypatch.setattr(req_check, "check", checks)
    fetched: list[int] = []

    def statement() -> str:
        fetched.append(1)
        return f"statement {len(fetched)}"

    log = tmp_path / "log.jsonl"
    return phase.PhaseGate(log, toolbox.load(), statement), checks


def _events(gate: phase.PhaseGate) -> list[object]:
    return [e["event"] for e in session_log.read(gate.log)]


def test_code_before_req_is_refused_and_never_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate, _ = _gate(tmp_path, monkeypatch)
    sent, note = gate.screen(CODE)
    assert sent is None
    assert "req:" in note
    assert _events(gate) == []
    assert gate.screen("what is the constraint?") == ("what is the constraint?", "")


def test_a_passing_list_opens_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    passed = req_check.Check("pass", (), "haiku")
    gate, checks = _gate(tmp_path, monkeypatch, passed, passed)
    sent, note = gate.screen("req: one pass, no extra memory")
    assert sent == "req: one pass, no extra memory\n\n[req check: pass]"
    assert note == "[req list accepted -- code is open]"
    assert gate.screen(CODE) == (CODE, "")
    assert gate.code_seen()
    events = session_log.read(gate.log)
    assert [e["event"] for e in events] == ["req", "req_check", "code"]
    assert events[1]["verdict"] == "pass"
    assert "req_incomplete" not in events[2]
    gate.screen("req: again")
    assert checks.statements == ["statement 1", "statement 1"]  # fetched once


def test_incomplete_blocks_until_the_third_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = req_check.Check("incomplete", ("self-inverse",), "haiku")
    gate, _ = _gate(tmp_path, monkeypatch, missing, missing, missing)
    sent, note = gate.screen("req: loop over it")
    assert sent is not None
    assert sent.endswith("[req check: incomplete; missing properties: self-inverse]")
    assert "self-inverse: applying it twice with the same value undoes it" in note
    assert "XOR" not in note
    assert "1 of 3" in note
    refused, why = gate.screen(CODE)
    assert refused is None
    assert "still incomplete" in why
    gate.screen("req: v2")
    _, last = gate.screen("req: v3")
    assert "accepted anyway" in last
    assert gate.screen(CODE) == (CODE, "")
    code = session_log.read(gate.log)[-1]
    assert code["event"] == "code"
    assert code["req_incomplete"] is True


def test_unverified_fails_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gate, _ = _gate(tmp_path, monkeypatch, req_check.Check("unverified"))
    _, note = gate.screen("req: something")
    assert "unverified" in note
    assert gate.screen(CODE) == (CODE, "")


def test_ambiguous_blocks_go_to_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate, _ = _gate(tmp_path, monkeypatch)
    asked: list[str] = []

    def classify(block: str, _ask: object = None) -> bool:
        asked.append(block)
        return block == "x ^= y"

    monkeypatch.setattr(req_check, "looks_like_code", classify)
    assert gate.screen("is it x ^ y?") == ("is it x ^ y?", "")
    assert gate.screen("x ^= y")[0] is None
    assert asked == ["is it x ^ y?", "x ^= y"]


def test_reveal_and_rungs_are_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate, _ = _gate(tmp_path, monkeypatch)
    assert gate.screen(" reveal ") == (" reveal ", "")
    assert gate.after_reply("Try it?\n<!-- rung:H2 -->") == "Try it?"
    assert gate.after_reply("Plain?") == "Plain?"
    events = session_log.read(gate.log)
    assert [e["event"] for e in events] == ["reveal", "rung"]
    assert events[1]["rung"] == "H2"


def test_leaks_only_before_code_and_never_what_kuhy_typed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate, _ = _gate(tmp_path, monkeypatch, req_check.Check("pass"))
    reply = "Think about XOR and a hash map."
    assert gate.leaks(reply, ["hm"]) == ["XOR", "hash map"]
    assert gate.leaks(reply, ["is it XOR?"]) == ["hash map"]
    assert gate.leaks(reply, ["reveal"]) == []
    gate.screen("req: x")
    gate.screen(CODE)
    assert gate.leaks(reply, []) == []


def test_a_statement_naming_an_entry_lets_the_coach_restate_it(
    tmp_path: Path,
) -> None:
    gate = phase.PhaseGate(tmp_path / "l.jsonl", toolbox.load(), lambda: "Use XOR.")
    assert gate.leaks("XOR here", []) == []


def test_open_exports_the_log_path_for_the_hooks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(local_session, "fetched_statement", lambda _p: None)
    gate = phase.PhaseGate.open("https://leetcode.com/problems/missing-number/")
    assert os.environ[session_log.LOG_ENV] == str(gate.log)
    assert gate.log.name.endswith("-missing-number.jsonl")
    assert gate.statement() == "missing-number"
    assert gate.toolbox.entries
