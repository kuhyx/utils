# Copyright (c) 2026 Krzysztof Rudnicki
"""The CLI: each subcommand reaches the right module with the right arguments."""

import json
from pathlib import Path
from typing import Any

import pytest

from game_recording import cli, finalize, library, supervise
from game_recording.options import RunOptions
from game_recording.tests.test_helpers import CONFIG

DOC = {
    "session": "s1",
    "tag": "v02",
    "video": {"start_s": 0.0, "duration_s": 10.0, "end_s": 10.0, "file": "s1.mkv"},
    "sync": {"approx": False},
    "events": [{"t": 1.0, "label": "pause_open"}],
}


@pytest.fixture
def rec_dir(tmp_path: Path) -> Path:
    (tmp_path / "s1.events.json").write_text(json.dumps(DOC), encoding="utf-8")
    return tmp_path


def run_cli(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    code = cli.main(list(argv), CONFIG)
    return code, capsys.readouterr().out


def test_wrap_passes_the_command_after_the_double_dash_and_the_options(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[Any, ...]] = []

    def fake_run(command: list[str], config: object, options: RunOptions) -> int:
        calls.append((command, config, options))
        return 4

    monkeypatch.setattr(supervise, "run", fake_run)
    code, _ = run_cli(capsys, "wrap", "--force", "--fps", "60", "--max-seconds", "2", "--", "godot", "--dev")
    assert code == 4
    assert calls == [
        (["godot", "--dev"], CONFIG, RunOptions(force=True, session="", audio="default", fps=60, max_seconds=2.0))
    ]


def test_wrap_without_a_double_dash_takes_the_command_as_given(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[list[str], RunOptions]] = []

    def fake_run(command: list[str], config: object, options: RunOptions) -> int:
        calls.append((command, options))
        return 0

    monkeypatch.setattr(supervise, "run", fake_run)
    run_cli(capsys, "wrap", "--session", "x", "--audio", "lavfi", "game")
    assert calls[0][0] == ["game"]
    assert calls[0][1].session == "x"
    assert calls[0][1].audio == "lavfi"


def test_finalize_rebuilds_the_events_of_one_rec_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[Path, object]] = []
    monkeypatch.setattr(finalize, "finalize", lambda meta, moment_map: calls.append((meta, moment_map)))
    assert run_cli(capsys, "finalize", "/r/s1.rec.json")[0] == 0
    assert calls == [(Path("/r/s1.rec.json"), CONFIG.moments)]


def test_list_prints_the_library(rec_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_cli(capsys, "list", "--dir", str(rec_dir)) == (0, "s1  00:10.000  1 moments  v02\n")


def test_latest_prints_the_moments_of_the_session(rec_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run_cli(capsys, "latest", "--dir", str(rec_dir), "--session", "s1")
    assert code == 0
    assert "pause_open" in out


def test_open_dry_run_prints_the_player_command(rec_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run_cli(capsys, "open", "1", "--dir", str(rec_dir), "--dry-run")
    assert code == 0
    assert out.startswith("mpv ")
    assert out.strip().endswith("s1.mkv")


def test_open_without_dry_run_reaches_the_player(
    rec_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[tuple[int | None, bool]] = []

    def fake_open(doc: object, directory: Path, n: int | None, *, dry_run: bool) -> int:
        seen.append((n, dry_run))
        return 3

    monkeypatch.setattr(library, "open_moment", fake_open)
    assert run_cli(capsys, "open", "--dir", str(rec_dir))[0] == 3
    assert seen == [(None, False)]


def test_open_of_a_missing_moment_exits_with_the_message(rec_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        run_cli(capsys, "open", "9", "--dir", str(rec_dir), "--dry-run")
    assert str(raised.value) == "no moment 9 (1..1)"


def test_a_session_that_matches_nothing_exits_with_the_message(
    rec_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        run_cli(capsys, "latest", "--dir", str(rec_dir), "--session", "zzz")
    assert str(raised.value) == f"no recordings in {rec_dir}"


def test_the_default_dir_is_the_feedback_recordings_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_BINARIES", "/b")
    assert cli.default_dir(CONFIG) == Path("/b/feedback/recordings")


def test_list_without_dir_uses_the_default_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rec = tmp_path / "feedback" / "recordings"
    rec.mkdir(parents=True)
    (rec / "s1.events.json").write_text(json.dumps(DOC), encoding="utf-8")
    monkeypatch.setenv("DEMO_BINARIES", str(tmp_path))
    assert run_cli(capsys, "list") == (0, "s1  00:10.000  1 moments  v02\n")


def test_a_missing_subcommand_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main([], CONFIG)
    assert raised.value.code == 2
