"""`skeleton-open`: only after a code attempt, logged, the sheet byte for byte.

The stop gate lets a sheet through only when the reply quotes this command's
stdout verbatim, so stdout is the sheet file and nothing else; the one
confirmation line goes to stderr.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from leetcode_coach import review_cli, session_log
from leetcode_coach.tests._review_support import fake_guard

if TYPE_CHECKING:
    from pathlib import Path

# Bare fences, tabs, no final newline: nothing a "helpful" print would keep.
SHEET = "# hashing\n\n```\nfunction solve(xs: number[]) {\n\t// HOLE: remember?\n}\n```"


def _sheet(text: str = SHEET) -> None:
    review_cli.SKELETON_DIR.mkdir(parents=True, exist_ok=True)
    (review_cli.SKELETON_DIR / "DOCS-hashing.md").write_bytes(text.encode())


def _logged(slug: str = "two-sum") -> list[tuple[str, object]]:
    events = session_log.read(session_log.log_path(slug))
    return [(e["event"], e.get("unit")) for e in events]


def test_after_code_stdout_is_the_sheet_unchanged_and_the_opening_is_logged(
    capfdbinary: pytest.CaptureFixture[bytes],
) -> None:
    _sheet()
    session_log.append(session_log.log_path("two-sum"), "code")
    assert review_cli.main(["skeleton-open", "two-sum", "hashing"]) == 0
    captured = capfdbinary.readouterr()
    assert captured.out == SHEET.encode()
    assert captured.err == b"skeleton logged: two-sum, unit hashing\n"
    assert _logged() == [("code", None), ("skeleton", "hashing")]


def test_code_from_an_earlier_day_counts(capsys: pytest.CaptureFixture[str]) -> None:
    _sheet(SHEET + "\n")
    old = session_log.sessions_dir() / "2026-10-01-two-sum.jsonl"
    session_log.append(old, "code")
    assert review_cli.main(["skeleton-open", "two-sum", "hashing"]) == 0
    assert capsys.readouterr().out == SHEET + "\n"
    assert _logged() == [("skeleton", "hashing")]


def test_a_flagged_solve_is_a_code_attempt_for_a_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _sheet()
    fake_guard(tmp_path, monkeypatch, "two-sum")
    assert review_cli.main(["skeleton-open", "two-sum", "hashing"]) == 0
    assert capsys.readouterr().out == SHEET
    assert _logged() == [("skeleton", "hashing")]


def test_before_any_code_the_sheet_stays_shut(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _sheet()
    fake_guard(tmp_path, monkeypatch, "3sum")
    session_log.append(session_log.log_path("two-sum"), "req", text="req: a")
    code = review_cli.main(["skeleton-open", "two-sum", "hashing"])
    assert code == review_cli.EXIT_REFUSED
    out = capsys.readouterr().out
    assert out.startswith("refused: two-sum has no code attempt yet")
    assert "HOLE" not in out
    assert _logged() == [("req", None)]


def test_no_code_and_no_guard_is_could_not_check(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _sheet()
    code = review_cli.main(["skeleton-open", "two-sum", "hashing"])
    assert code == review_cli.EXIT_UNCHECKED
    out = capsys.readouterr().out
    assert out.startswith("could not check: ")
    assert "HOLE" not in out
    assert _logged() == []


def test_a_missing_sheet_is_an_error_and_logs_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_log.append(session_log.log_path("two-sum"), "code")
    code = review_cli.main(["skeleton-open", "two-sum", "hashing"])
    assert code == review_cli.EXIT_REFUSED
    assert capsys.readouterr().out.startswith(
        "refused: no skeleton sheet for unit 'hashing' at "
    )
    assert _logged() == [("code", None)]


@pytest.mark.parametrize(
    ("slug", "unit", "why"),
    [
        ("two-sum", "../SKILL", "not a unit id"),
        ("two-sum", "Hashing", "not a unit id"),
        ("Two Sum", "hashing", "not a LeetCode problem URL or slug"),
    ],
)
def test_bad_names_are_refused(
    capsys: pytest.CaptureFixture[str], slug: str, unit: str, why: str
) -> None:
    _sheet()
    assert review_cli.main(["skeleton-open", slug, unit]) == review_cli.EXIT_REFUSED
    assert why in capsys.readouterr().out
    assert _logged() == []
