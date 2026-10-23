"""Tests for the coach's JSONL session log (contract read by leetcode_guard)."""

from __future__ import annotations

from datetime import date, datetime
import json
import logging
from typing import TYPE_CHECKING

import pytest

from leetcode_coach import session_log
from leetcode_guard import _coach_log

if TYPE_CHECKING:
    from pathlib import Path


def test_sessions_dir_follows_the_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert session_log.sessions_dir() == tmp_path / "sessions"
    monkeypatch.setenv(session_log.SESSIONS_ENV, "")
    assert session_log.sessions_dir() == session_log.DEFAULT_DIR


@pytest.mark.parametrize(
    ("problem", "slug"),
    [
        ("https://leetcode.com/problems/missing-number/description/", "missing-number"),
        ("single-number", "single-number"),
        ("Weird Name!", "weird-name"),
        ("!!!", "problem"),
    ],
)
def test_log_path_is_dated_and_slugged(tmp_path: Path, problem: str, slug: str) -> None:
    path = session_log.log_path(problem, date(2026, 10, 23))
    assert path == tmp_path / "sessions" / f"2026-10-23-{slug}.jsonl"


def test_log_path_defaults_to_today() -> None:
    assert session_log.log_path("x").name.startswith(date.today().isoformat())


def test_append_writes_one_timestamped_object_per_line(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "log.jsonl"
    session_log.append(path, "req", text="req: a")
    session_log.append(path, "req_check", verdict="pass", missing=[])
    lines = path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    assert first["event"] == "req"
    assert first["text"] == "req: a"
    assert datetime.fromisoformat(first["ts"]).tzinfo is not None
    assert json.loads(lines[1])["verdict"] == "pass"


def test_append_refuses_an_event_outside_the_contract(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="req_incomplete"):
        session_log.append(tmp_path / "x.jsonl", "req_incomplete")


def test_read_tolerates_a_missing_file_and_torn_lines(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "log.jsonl"
    assert session_log.read(path) == []
    path.write_text('{"event": "code"}\n{"event": \n[1]\n\n', encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="leetcode_coach.session_log"):
        assert session_log.read(path) == [{"event": "code"}]
    assert "not JSON" in caplog.text
    assert session_log.has_code(path)
    assert not session_log.has_code(tmp_path / "other.jsonl")


def test_the_status_reader_understands_what_is_written(tmp_path: Path) -> None:
    path = tmp_path / "2026-10-23-missing-number.jsonl"
    session_log.append(path, "req", text="req: x", cluster="bit-cancellation")
    session_log.append(path, "req_check", verdict="incomplete", missing=["p"])
    session_log.append(path, "code", req_incomplete=True)
    session_log.append(path, "rung", rung="H2")
    problem = _coach_log.read_session(path)
    assert problem == _coach_log.CoachProblem(
        slug="missing-number",
        cluster="bit-cancellation",
        req_before_code=True,
        max_rung="H2",
        revealed=False,
        req_check="incomplete",
        day="2026-10-23",
    )
