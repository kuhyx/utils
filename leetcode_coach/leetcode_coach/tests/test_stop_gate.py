"""Tests for the /leetcode no-solution Stop hook (moved from ~/.claude/hooks)."""

from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

from leetcode_coach import stop_gate

REPO = Path(stop_gate.__file__).resolve().parents[1]
SHIM = REPO / "leetcode_coach" / "hook_shims" / "leetcode_no_solution_stop.py"
SLASH_LOAD = {
    "type": "user",
    "message": {
        "content": "<command-message>leetcode</command-message>\n"
        "<command-name>/leetcode</command-name>"
    },
}
STARTER = {
    "type": "user",
    "message": {"content": "## Starter code\nfunction sortPeople(names, heights) {"},
}
SOLUTION = (
    "Fix: `return names.map((n, i) => [n, heights[i]]).sort((a, b) => b[1] - a[1]);`"
)


def _skill_load(base: str) -> dict[str, Any]:
    text = f"Base directory for this skill: {base}\n\n# /leetcode"
    return {"type": "user", "message": {"content": [{"type": "text", "text": text}]}}


def _raw(*entries: dict[str, Any]) -> str:
    return "".join(json.dumps(e, separators=(",", ":")) + "\n" for e in entries)


@pytest.mark.parametrize(
    "load",
    [
        SLASH_LOAD,
        _skill_load(str(Path.home() / ".claude" / "skills" / "leetcode")),
        _skill_load(str(Path(stop_gate.__file__).resolve().parent)),
    ],
)
def test_gate_arms_on_every_load_kind(load: dict[str, Any]) -> None:
    reason = stop_gate.verdict(_raw(load, STARTER), SOLUTION)
    assert reason is not None
    assert reason.startswith("leetcode gate: your reply hands kuhy code they can paste")
    assert "`return names.map((n, i) => [n, heights[i]]).sort((a, b) =>" in reason


def test_gate_idle_without_load_reply_reveal_or_starter() -> None:
    assert stop_gate.verdict(_raw(STARTER), SOLUTION) is None
    assert stop_gate.verdict(_raw(SLASH_LOAD, STARTER), "") is None
    reveal = {"type": "user", "message": {"content": "reveal"}}
    assert stop_gate.verdict(_raw(SLASH_LOAD, STARTER, reveal), SOLUTION) is None
    assert stop_gate.verdict(_raw(SLASH_LOAD), SOLUTION) is None
    assert stop_gate.verdict(_raw(SLASH_LOAD, STARTER), "What is `names`?") is None


def test_blocks_are_counted_per_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(stop_gate, "STATE_DIR", tmp_path / "state")
    assert [stop_gate.blocks_so_far("s", "p1") for _ in range(3)] == [0, 1, 2]
    assert stop_gate.blocks_so_far("s", "p2") == 0
    assert (tmp_path / "state" / "s.blocks").read_text(encoding="utf-8") == (
        "p1\np1\np1\np2\n"
    )


def _main(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    event: dict[str, Any],
) -> str:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    assert stop_gate.main() == 0
    return capsys.readouterr().out


def test_main_blocks_then_fails_open_at_the_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(stop_gate, "STATE_DIR", tmp_path / "state")
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(_raw(SLASH_LOAD, STARTER), encoding="utf-8")
    event = {
        "transcript_path": str(transcript),
        "last_assistant_message": SOLUTION,
        "session_id": "s",
        "prompt_id": "p",
    }
    outs = [_main(monkeypatch, capsys, event) for _ in range(stop_gate.MAX_BLOCKS + 1)]
    first = json.loads(outs[0])
    assert first["decision"] == "block"
    assert first["reason"] == stop_gate.verdict(transcript.read_text(), SOLUTION)
    assert outs[1] == outs[0]
    assert outs[-1] == ""


def test_main_passes_without_transcript_or_verdict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _main(monkeypatch, capsys, {"transcript_path": str(tmp_path / "no")}) == ""
    assert _main(monkeypatch, capsys, {}) == ""
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(_raw(STARTER), encoding="utf-8")
    event = {"transcript_path": str(transcript), "last_assistant_message": SOLUTION}
    assert _main(monkeypatch, capsys, event) == ""


def test_hook_shim_execs_the_package_gate(tmp_path: Path) -> None:
    """The ~/.claude/hooks shim hands stdin to `-m leetcode_coach.stop_gate`."""
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(_raw(SLASH_LOAD, STARTER), encoding="utf-8")
    event = {
        "transcript_path": str(transcript),
        "last_assistant_message": SOLUTION,
        "session_id": f"shim-test-{tmp_path.name}",
        "prompt_id": "p",
    }
    assert len(SHIM.read_text(encoding="utf-8").splitlines()) <= 3
    proc = subprocess.run(
        [sys.executable, str(SHIM)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        # -P in the shim keeps cwd off sys.path; the real hook finds the
        # package through install.sh's editable install, this test through
        # PYTHONPATH (which -P still honours). HOME keeps the block counter
        # out of the real ~/.claude/state.
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO)},
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["decision"] == "block"
