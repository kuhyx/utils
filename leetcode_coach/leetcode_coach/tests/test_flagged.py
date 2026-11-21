"""The coach reads the guard's flagged report through the guard CLI only."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from leetcode_coach import flagged
from leetcode_coach.tests._review_support import (
    REAL_GUARD_COMMAND,
    fake_guard,
    flagged_row,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_the_real_command_is_the_guard_cli_on_this_interpreter() -> None:
    assert (
        sys.executable,
        "-m",
        "leetcode_guard",
        "--flagged",
        "--json",
    ) == REAL_GUARD_COMMAND


def test_rows_come_back_as_the_guard_printed_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_guard(tmp_path, monkeypatch, "two-sum", "3sum")
    assert flagged.flagged_rows() == [flagged_row("two-sum"), flagged_row("3sum")]
    assert flagged.flagged_slugs() == {"two-sum", "3sum"}


def test_an_empty_report_is_an_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_guard(tmp_path, monkeypatch)
    assert flagged.flagged_rows() == []


@pytest.mark.parametrize(
    ("stdout", "code", "why"),
    [
        ('{"flagged": []}', 3, "exit 3: guard said no"),
        ("Traceback", 0, "not JSON"),
        ('{"measured": []}', 0, "no flagged list"),
        ('{"flagged": {}}', 0, "no flagged list"),
        ("[]", 0, "no flagged list"),
        ('{"flagged": [{"active_seconds": 5}]}', 0, "without a slug"),
        ('{"flagged": ["two-sum"]}', 0, "without a slug"),
    ],
)
def test_a_guard_that_cannot_answer_is_could_not_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stdout: str, code: int, why: str
) -> None:
    fake_guard(tmp_path, monkeypatch, stdout=stdout, code=code)
    with pytest.raises(flagged.CouldNotCheckError, match=why):
        flagged.flagged_rows()


def test_a_missing_guard_is_could_not_check() -> None:
    with pytest.raises(flagged.CouldNotCheckError, match="did not run"):
        flagged.flagged_rows()


def test_a_hung_guard_is_could_not_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_guard(tmp_path, monkeypatch, sleep=5)
    monkeypatch.setattr(flagged, "GUARD_TIMEOUT_SECONDS", 0.2)
    with pytest.raises(flagged.CouldNotCheckError, match="did not run"):
        flagged.flagged_rows()


def test_the_evidence_line_shows_what_the_guard_measured() -> None:
    assert flagged.evidence_line(flagged_row("two-sum")) == (
        "two-sum  accepted 2026-11-21T18:01:34+01:00  active 25m  span 40m"
        "  failed Wrong Answer 2  first submit 12m"
        "  tabs description 20m, solutions 5m  theory done"
    )


def test_the_evidence_line_survives_a_sparse_row() -> None:
    assert flagged.evidence_line({"slug": "3sum", "span_seconds": None}) == (
        "3sum  accepted n/a  active n/a  span n/a"
        "  failed none  first submit n/a  tabs none  theory n/a"
    )
