"""Tests for ``history.py``: kuhy's own attempts on one problem, for the coach.

The guard's harvester mirrors every submission with its code into
``~/.local/share/leetcode_guard/history/<slug>.json`` (phase 2, 2026-11-22).
The coach reads it as context, read-only, bounded.
"""

from __future__ import annotations

import json
import runpy
import sys
from typing import TYPE_CHECKING

import pytest

from leetcode_coach import history

if TYPE_CHECKING:
    from pathlib import Path

MIRROR = {
    "slug": "two-sum",
    "fetched_at": 1795287060,
    "complete": True,
    "next_offset": 0,
    "submissions": [
        {
            "id": "3",
            "status": "Accepted",
            "lang": "python3",
            "timestamp": 1795287000,
            "runtime": "40 ms",
            "memory": "17 MB",
            "code": "class Solution:\n    def twoSum(self): return seen",
        },
        {
            "id": "2",
            "status": "Wrong Answer",
            "lang": "python3",
            "timestamp": 1795286000,
            "runtime": "N/A",
            "memory": "N/A",
            "code": "x" * 5000,
        },
        {
            "id": "1",
            "status": "Compile Error",
            "lang": "python3",
            "timestamp": 1795285000,
            "runtime": "N/A",
            "memory": "N/A",
        },
    ],
}


@pytest.fixture(name="mirror_dir")
def _mirror_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A scratch history dir; the real one is never read."""
    folder = tmp_path / "history"
    folder.mkdir()
    monkeypatch.setattr(history, "HISTORY_DIR", folder)
    return folder


def write(folder: Path, data: object, slug: str = "two-sum") -> None:
    """Put one mirror file down."""
    (folder / f"{slug}.json").write_text(json.dumps(data), encoding="utf-8")


def test_every_attempt_is_listed_newest_first_with_code(mirror_dir: Path):
    """Failed and accepted alike, each with its status, and code where fetched."""
    write(mirror_dir, MIRROR)

    text = history.render("two-sum")

    assert (
        text.index("Accepted")
        < text.index("Wrong Answer")
        < text.index("Compile Error")
    )
    assert "return seen" in text
    assert "(code not mirrored yet)" in text
    assert "3 submissions (1 accepted)" in text


def test_long_code_is_cut(mirror_dir: Path):
    """One huge paste must not flood the coach's context."""
    write(mirror_dir, MIRROR)

    text = history.render("two-sum")

    assert "x" * history.CODE_CHARS in text
    assert "x" * (history.CODE_CHARS + 1) not in text
    assert "[cut]" in text


def test_only_the_newest_submissions_are_shown(mirror_dir: Path):
    """A problem with 60 attempts shows the newest few and says how many more."""
    rows = [
        {"id": str(n), "status": "Wrong Answer", "timestamp": 1795280000 + n}
        for n in range(60)
    ]
    write(mirror_dir, {**MIRROR, "submissions": rows})

    text = history.render("two-sum")

    assert text.count("Wrong Answer") == history.SHOWN
    assert f"{60 - history.SHOWN} older not shown" in text


def test_no_mirror_says_so(mirror_dir: Path):
    """No file yet (never submitted, or the harvester has not reached it)."""
    assert mirror_dir.exists()
    assert history.render("two-sum") == "No mirrored submissions for two-sum yet."


@pytest.mark.parametrize("data", ["{", [], {"submissions": 3}])
def test_an_unreadable_mirror_is_reported_not_trusted(mirror_dir: Path, data: object):
    """Hand-edited or half-written: say it is unreadable, never crash."""
    path = mirror_dir / "two-sum.json"
    path.write_text(
        data if isinstance(data, str) else json.dumps(data), encoding="utf-8"
    )

    assert (
        history.render("two-sum") == "The submission mirror for two-sum is unreadable."
    )


def test_a_bad_slug_is_refused(mirror_dir: Path):
    """``../x`` is not a slug and never becomes a path."""
    assert mirror_dir.exists()
    with pytest.raises(ValueError, match="not a LeetCode slug"):
        history.render("../escape")


def test_cli_prints_and_takes_a_url(
    mirror_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """Run by path like fetch_problem.py: a URL or a slug, exit 0."""
    write(mirror_dir, MIRROR)
    monkeypatch.setattr(
        sys,
        "argv",
        ["history.py", "https://leetcode.com/problems/two-sum/description/"],
    )

    assert history.main() == 0
    assert "Accepted" in capsys.readouterr().out


def test_cli_rejects_garbage(
    mirror_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """Exit 1 with one stderr line, like fetch_problem.py's bad input."""
    assert mirror_dir.exists()
    monkeypatch.setattr(sys, "argv", ["history.py", "../x"])

    assert history.main() == 1
    assert "not a LeetCode slug" in capsys.readouterr().err


def test_runs_as_a_script(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """``python3 history.py <slug>`` works without the package installed."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["history.py", "two-sum"])

    with pytest.raises(SystemExit) as stop:
        runpy.run_path(history.__file__, run_name="__main__")

    assert stop.value.code == 0


def test_cli_wants_exactly_one_problem(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """No argument: the usage line on stderr, exit 1."""
    monkeypatch.setattr(sys, "argv", ["history.py"])

    assert history.main() == 1
    assert "usage" in capsys.readouterr().err


def test_a_row_without_a_timestamp_still_prints(mirror_dir: Path):
    """A hand-edited row missing its time shows ``?``, never crashes."""
    write(mirror_dir, {**MIRROR, "submissions": [{"id": "9", "status": "Accepted"}]})

    assert "### Accepted - ? - ?, ?, ?" in history.render("two-sum")
