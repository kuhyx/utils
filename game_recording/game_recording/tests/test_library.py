# Copyright (c) 2026 Krzysztof Rudnicki
"""Listing and opening a recording at a moment."""

import json
import os
from pathlib import Path
import subprocess
from typing import Any

import pytest

from game_recording import library

DOC: dict[str, Any] = {
    "session": "s1",
    "tag": "v02",
    "video": {"start_s": 0.052, "duration_s": 100.0, "end_s": 100.052, "file": "s1.mkv"},
    "sync": {"approx": False},
    "events": [
        {"t": -2.0, "label": "game_start watch", "before_recording": True},
        {"t": 1.0, "label": "pause_open"},
        {"t": 42.5, "label": "command rally"},
        {"t": 400.0, "label": "late", "after_recording": True},
    ],
}

PARTED: dict[str, Any] = {
    "session": "s2",
    "video": {
        "start_s": 0.05,
        "duration_s": 30.0,
        "end_s": 30.05,
        "file": "s2.mkv",
        "parts": [
            {"file": "s2.mkv", "start_s": 0.05, "duration_s": 10.0},
            {"file": "s2.part2.mkv", "start_s": 20.0, "duration_s": 10.0},
        ],
    },
    "sync": {"approx": False},
    "events": [
        {"t": 5.0, "label": "a", "file": "s2.mkv"},
        {"t": 15.0, "label": "in the gap", "in_gap": True},
        {"t": 21.0, "label": "b", "file": "s2.part2.mkv"},
    ],
}


def write(folder: Path, name: str, doc: dict[str, Any], mtime: int) -> Path:
    path = folder / f"{name}.events.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


@pytest.mark.parametrize(("seconds", "text"), [(75.5, "01:15.500"), (0.0, "00:00.000"), (-1.5, "-00:01.500")])
def test_stamp_is_minutes_seconds_millis(seconds: float, text: str) -> None:
    assert library.stamp(seconds) == text


def test_table_numbers_only_moments_inside_the_file() -> None:
    lines = library.table(DOC).splitlines()
    assert lines[0] == "s1  v02  01:40.000  s1.mkv"
    assert len(lines) == 3
    assert lines[1] == "  1  00:01.000  pause_open"
    assert lines[2] == "  2  00:42.500  command rally"


def test_open_seeks_a_little_before_the_moment_on_the_files_own_timeline() -> None:
    cmd = library.open_command(DOC, Path("/rec"), 2)
    assert cmd[0] == "mpv"
    assert "--rebase-start-time=no" in cmd
    assert "--start=39.500" in cmd
    assert cmd[-1] == "/rec/s1.mkv"


def test_open_never_seeks_before_the_first_frame() -> None:
    assert "--start=0.052" in library.open_command(DOC, Path("/rec"), 1)


def test_open_without_a_number_plays_from_the_start() -> None:
    assert not any(a.startswith("--start") for a in library.open_command(DOC, Path("/rec"), None))


def test_open_of_a_missing_moment_says_the_range() -> None:
    with pytest.raises(IndexError, match=r"no moment 9 \(1\.\.2\)"):
        library.open_command(DOC, Path("/rec"), 9)


def test_gap_moments_are_not_listed() -> None:
    assert [e["label"] for e in library.shown(PARTED)] == ["a", "b"]


def test_open_uses_the_part_that_holds_the_moment() -> None:
    cmd = library.open_command(PARTED, Path("/rec"), 2)
    assert cmd[-1] == "/rec/s2.part2.mkv"
    assert "--start=20.000" in cmd, "clamped to the part's first frame, not 18.0"


def test_the_table_says_the_window_went_away() -> None:
    text = library.table(PARTED)
    assert "2 parts" in text
    assert "[s2.part2.mkv]" in text


def test_sessions_are_listed_newest_first_and_load_back(tmp_path: Path) -> None:
    old = write(tmp_path, "old", {**DOC, "session": "old"}, 1_000)
    new = write(tmp_path, "new", {**DOC, "session": "new"}, 2_000)
    assert library.sessions(tmp_path) == [new, old]
    assert library.load(new)["session"] == "new"


def test_the_listing_has_one_line_per_session(tmp_path: Path) -> None:
    write(tmp_path, "a", DOC, 1_000)
    assert library.listing(tmp_path) == "s1  01:40.000  2 moments  v02"
    assert library.listing(tmp_path / "none") == ""


def test_a_png_and_an_approximate_sync_show_in_the_table() -> None:
    doc = {**DOC, "sync": {"approx": True}, "events": [{"t": -1.5, "label": "x", "png": "x.png"}]}
    lines = library.table(doc).splitlines()
    assert "+-1 s" in lines[1]
    assert lines[2] == "  1  -00:01.500  x  x.png"


def test_open_moment_prints_the_command_on_a_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    assert library.open_moment(DOC, Path("/rec"), 2, dry_run=True) == 0
    assert capsys.readouterr().out.split() == [
        "mpv",
        "--rebase-start-time=no",
        "--force-window=yes",
        "--start=39.500",
        "/rec/s1.mkv",
    ]


def test_open_moment_runs_the_player_and_returns_its_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def call(cmd: list[str]) -> int:
        seen.append(cmd)
        return 3

    monkeypatch.setattr(subprocess, "call", call)
    assert library.open_moment(DOC, Path("/rec"), None, dry_run=False) == 3
    assert seen[0][-1] == "/rec/s1.mkv"
