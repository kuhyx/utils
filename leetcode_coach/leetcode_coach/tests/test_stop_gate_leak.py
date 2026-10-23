"""Tests for the Stop hook's leak bounce: no toolbox name before kuhy's first code."""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING, Any

from leetcode_coach import session_log, stop_gate

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

SLASH_LOAD = {
    "type": "user",
    "message": {
        "content": "<command-message>leetcode</command-message>\n"
        "<command-name>/leetcode</command-name>"
    },
}
LEAKY = "Think about XOR: what does a value do to itself?"


def _user(text: str) -> dict[str, Any]:
    return {"type": "user", "message": {"content": [{"type": "text", "text": text}]}}


def _raw(*entries: dict[str, Any]) -> str:
    return "".join(json.dumps(e, separators=(",", ":")) + "\n" for e in entries)


def test_a_reply_naming_an_entry_before_code_is_bounced() -> None:
    reason = stop_gate.verdict(_raw(SLASH_LOAD, _user("no idea")), LEAKY)
    assert reason is not None
    assert reason.startswith("leetcode gate: your reply names XOR")
    assert "properties" in reason


def test_is_it_xor_gets_an_honest_answer() -> None:
    raw = _raw(SLASH_LOAD, _user("is it XOR?"))
    assert stop_gate.verdict(raw, "Yes, XOR. What is x ^ x?") is None


def test_the_bounce_reason_does_not_whitelist_itself() -> None:
    feedback = _user("Stop hook feedback: leetcode gate: your reply names XOR")
    assert stop_gate.verdict(_raw(SLASH_LOAD, feedback), LEAKY) is not None


def test_names_in_the_fetched_statement_may_be_restated() -> None:
    tool = {
        "type": "user",
        "message": {
            "content": [{"type": "tool_result", "content": "Solve it with XOR."}]
        },
    }
    assert stop_gate.verdict(_raw(SLASH_LOAD, tool), LEAKY) is None


def test_the_session_log_lifts_the_bounce_once_code_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv(session_log.LOG_ENV, str(log))
    raw = _raw(SLASH_LOAD, _user("hmm"))
    assert stop_gate.verdict(raw, LEAKY) is not None
    session_log.append(log, "code")
    assert stop_gate.verdict(raw, LEAKY) is None


def test_without_a_log_kuhys_own_code_lifts_it() -> None:
    """The TUI has no REPL and no log: kuhy's code in the transcript counts."""
    raw = _raw(SLASH_LOAD, _user("function f(nums) {\n  return 0;\n}"))
    assert stop_gate.verdict(raw, LEAKY) is None


def test_reveal_lifts_the_bounce() -> None:
    assert stop_gate.verdict(_raw(SLASH_LOAD, _user("reveal")), LEAKY) is None


def test_main_prints_the_leak_block(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(stop_gate, "STATE_DIR", tmp_path / "state")
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(_raw(SLASH_LOAD, _user("hmm")), encoding="utf-8")
    event = {
        "transcript_path": str(transcript),
        "last_assistant_message": LEAKY,
        "session_id": "s",
        "prompt_id": "p",
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    assert stop_gate.main() == 0
    assert json.loads(capsys.readouterr().out)["decision"] == "block"
