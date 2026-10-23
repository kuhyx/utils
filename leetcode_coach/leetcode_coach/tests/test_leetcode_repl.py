"""Tests for the print-mode /leetcode REPL and its hand-over to the local model."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import Any

import pytest

from leetcode_coach import claude_cli, leetcode_repl, local_session, report

LAUNCHER = Path(leetcode_repl.__file__).with_name("leetcode")


@pytest.mark.parametrize(
    ("reply", "hit"),
    [
        (
            {"result": "You've hit your session limit · resets 3pm (Europe/Warsaw)"},
            True,
        ),
        ({"result": "You\u2019ve hit your weekly limit · resets Mon"}, True),
        ({"result": "", "api_error_status": 429}, True),
        ({"result": "x", "_stderr": "Claude AI usage limit reached|1790427600"}, True),
        ({"result": "Does your loop hit every element?"}, False),
    ],
)
def test_is_limit_hit(reply: dict[str, Any], *, hit: bool) -> None:
    assert claude_cli.is_limit_hit(reply) is hit


def _fake_run(handed: dict[str, Any]) -> Any:
    def fake_run(
        problem: str,
        history: list[dict[str, str]],
        first: str,
        _r: object,
        **_kw: object,
    ) -> int:
        handed.update(problem=problem, history=history, first=first)
        return 0

    return fake_run


def test_limit_mid_session_falls_back_with_history(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    replies = iter(
        [
            {"result": "Restated. What feels unclear?", "session_id": "s1"},
            {"result": "You've hit your session limit · resets 8pm (Europe/Warsaw)"},
        ]
    )
    monkeypatch.setattr(leetcode_repl, "ask", lambda *_a: next(replies))
    monkeypatch.setattr(leetcode_repl, "read_block", lambda: "the hash map part")
    handed: dict[str, Any] = {}
    monkeypatch.setattr(local_session, "run", _fake_run(handed))
    assert leetcode_repl.main(["two-sum", "maps"]) == 0
    assert handed["problem"] == "two-sum"
    assert handed["first"] == "the hash map part"
    assert handed["history"][1]["content"] == "Restated. What feels unclear?"
    assert capsys.readouterr().out == (
        "Restated. What feels unclear?\n\n...\n"
        "[You've hit your session limit · resets 8pm (Europe/Warsaw) "
        "-- continuing locally]\n"
    )


def test_limit_on_the_first_turn_starts_locally(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(leetcode_repl, "ask", lambda *_a: {"api_error_status": 429})
    handed: dict[str, Any] = {}
    monkeypatch.setattr(local_session, "run", _fake_run(handed))
    assert leetcode_repl.run_claude("sonnet", ["two-sum"]) == 0
    assert handed["history"] == []
    assert "not said" in handed["first"]
    assert capsys.readouterr().out == "[usage limit -- switching to local model]\n"


def test_session_loop_until_quit_and_missing_session(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sent: list[tuple[list[str], str]] = []
    replies = iter([{"result": "Open?", "session_id": "s1"}, {"result": "Next?"}])

    def ask(args: list[str], prompt: str) -> dict[str, Any]:
        sent.append((args, prompt))
        return next(replies)

    blocks = iter(["my try", "quit"])
    monkeypatch.setattr(leetcode_repl, "ask", ask)
    monkeypatch.setattr(leetcode_repl, "read_block", lambda: next(blocks))
    assert leetcode_repl.run_claude("sonnet", ["two-sum", "maps"]) == 0
    assert sent == [
        (["--model", "sonnet"], "/leetcode two-sum maps"),
        (["--model", "sonnet", "--resume", "s1"], "my try"),
    ]
    assert capsys.readouterr().out == "Open?\n\n...\nNext?\n"
    monkeypatch.setattr(leetcode_repl, "ask", lambda *_a: {"result": "no id"})
    assert leetcode_repl.run_claude("sonnet", ["two-sum"]) == 1


def test_read_block_joins_lines_until_a_blank(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    lines = iter(["", "a", "b", ""])
    monkeypatch.setattr("builtins.input", lambda: next(lines))
    assert leetcode_repl.read_block() == "a\nb"
    assert capsys.readouterr().out == "\nyou> "

    def eof() -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    assert leetcode_repl.read_block() is None
    typed = iter(["x"])

    def then_eof() -> str:
        try:
            return next(typed)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr("builtins.input", then_eof)
    assert leetcode_repl.read_block() == "x"


def test_repl_defaults_to_sonnet(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.delenv("LEETCODE_MODEL", raising=False)
    monkeypatch.setattr(leetcode_repl, "run_claude", lambda m, _a: seen.append(m))
    leetcode_repl.main(["two-sum"])
    assert seen == ["sonnet"]


def test_local_flag_skips_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    handed: dict[str, Any] = {}
    monkeypatch.setattr(local_session, "run", _fake_run(handed))
    assert leetcode_repl.main(["--local", "two-sum", "loops"]) == 0
    assert handed["problem"] == "two-sum"
    assert handed["first"].endswith("stuck on: loops")


def test_report_is_a_subcommand(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def fake_report(argv: list[str]) -> int:
        seen.append(argv)
        return 0

    monkeypatch.setattr(report, "main", fake_report)
    assert leetcode_repl.main(["report"]) == 0
    assert seen == [[]]


def test_help_prints_usage(capsys: pytest.CaptureFixture[str]) -> None:
    assert leetcode_repl.main([]) == 0
    assert capsys.readouterr().out.startswith(
        "Usage: leetcode [--local] <url-or-slug> [what you are stuck on...]\n"
    )


def test_launcher_runs_the_package_repl() -> None:
    # The real launcher finds the package through install.sh's editable
    # install; PYTHONPATH stands in for it here (-P still honours it).
    env = {**os.environ, "PYTHONPATH": str(LAUNCHER.resolve().parents[1])}
    proc = subprocess.run(
        [str(LAUNCHER), "--help"], capture_output=True, text=True, check=False, env=env
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("Usage: leetcode [--local]")


def test_launcher_does_not_leak_pythonpath_into_the_session() -> None:
    """The REPL hands its environment to `claude -p`; the launcher adds nothing."""
    body = LAUNCHER.read_text(encoding="utf-8").split("set -euo pipefail", 1)[1]
    assert "PYTHONPATH" not in body
