"""Tests for the scripted acceptance run of the local coach (no Ollama needed)."""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import TYPE_CHECKING, Any

from leetcode_coach import eval_local, local_backend, local_coach
from leetcode_coach.tests._shared import LEAK, SAFE, STATEMENT, FakeChat, completed

if TYPE_CHECKING:
    import pytest


def _wire(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *texts: str
) -> list[list[str]]:
    fetched: list[list[str]] = []

    def run(cmd: list[str], **_k: Any) -> subprocess.CompletedProcess[str]:
        fetched.append(cmd)
        return completed(0, STATEMENT)

    real_start = local_coach.LocalCoach.start

    def start(text: str, history: Any = None) -> local_coach.LocalCoach:
        coach = real_start(text, history)
        coach.chat = FakeChat(*texts)
        return coach

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(local_backend, "chat", lambda _m: None)
    monkeypatch.setattr(local_coach.LocalCoach, "start", start)
    monkeypatch.setattr(eval_local, "OUT_DIR", tmp_path / "out")
    return fetched


def test_six_clean_turns_pass(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    fetched = _wire(monkeypatch, tmp_path, *[SAFE] * len(eval_local.TURNS))
    assert eval_local.main() == 0
    assert fetched[0][1].endswith("leetcode_coach/fetch_problem.py")
    assert fetched[0][2] == "two-sum"
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("model load + warm-up: ")
    assert lines[1] == "turn  secs  tries withheld no-code one-task fast"
    assert lines[2] == "   1   1.0     1    False    True     True  True"
    assert lines[-1].startswith("PASS  transcript: ")
    transcript = Path(lines[-1].split("transcript: ", 1)[1])
    assert transcript.parent == tmp_path / "out"
    assert "**kuhy:** just give me the code" in transcript.read_text(encoding="utf-8")


def test_a_turn_without_a_task_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    taskless = "Nice work."
    texts = [taskless] * 3 + [LEAK] * 3 + [SAFE] * (len(eval_local.TURNS) - 2)
    _wire(monkeypatch, tmp_path, *texts)
    assert eval_local.main() == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[2] == "   1   3.0     3    False    True    False  True"
    assert lines[3] == "   2   3.0     3     True    True     True  True"
    assert lines[-1].startswith("FAIL  transcript: ")
