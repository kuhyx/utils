"""Tests for `leetcode report` (its stdout is the interface)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_coach import report, session_log

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

HEADER = "problem" + " " * 29 + "req-before-code  max-rung  reveal  req_check"


def _row(*cols: str) -> str:
    return f"{cols[0]:<36}{cols[1]:<17}{cols[2]:<10}{cols[3]:<8}{cols[4]}"


def test_report_prints_one_row_per_problem(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "sessions"
    good = folder / "2026-10-22-missing-number.jsonl"
    session_log.append(good, "req", text="req: a")
    session_log.append(good, "req_check", verdict="incomplete", missing=["p"])
    session_log.append(good, "req", text="req: b")
    session_log.append(good, "req_check", verdict="pass", missing=[])
    session_log.append(good, "code")
    session_log.append(good, "rung", rung="H1")
    session_log.append(good, "rung", rung="H0")
    bad = folder / "2026-10-23-single-number.jsonl"
    session_log.append(bad, "code")
    session_log.append(bad, "rung", rung="H3")
    session_log.append(bad, "reveal")
    fresh = folder / "2026-10-23-two-sum.jsonl"
    session_log.append(fresh, "rung", rung="H9")
    assert report.main([]) == 0
    assert capsys.readouterr().out.splitlines() == [
        HEADER,
        _row("2026-10-22-missing-number", "y", "H1", "n", "incomplete,pass"),
        _row("2026-10-23-single-number", "n", "H3", "y", "-"),
        _row("2026-10-23-two-sum", "-", "-", "n", "-"),
    ]


def test_report_without_sessions_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert report.main([]) == 0
    assert capsys.readouterr().out == (
        f"no coach sessions yet in {tmp_path / 'sessions'}\n"
    )
