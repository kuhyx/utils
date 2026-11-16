# Copyright (c) 2026 Krzysztof Rudnicki
"""Recorder.step and its failure paths, with the process and window layers faked."""

from collections.abc import Callable
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest import mock

import pytest

from game_recording import gsr, procs, recorder, window
from game_recording.options import RecorderOptions
from game_recording.supervise import recording_paths
from game_recording.tests.test_helpers import SESSION

WIN = window.Window(id=0x4200007, width=1280, height=800)
OTHER = window.Window(id=0x4200008, width=800, height=600)
MakeRecorder = Callable[..., recorder.Recorder]


def proc_of(rec: recorder.Recorder) -> object:
    """The recorder's process, read without the type narrowing of an earlier assignment."""
    return rec.proc


def open_part_of(rec: recorder.Recorder) -> object:
    return rec.gsr.open_part


def alive() -> mock.Mock:
    return mock.Mock(poll=mock.Mock(return_value=None))


def running_ffmpeg() -> mock.Mock:
    """An ffmpeg that is still up when the settle wait ends."""
    proc = mock.Mock()
    proc.wait.side_effect = subprocess.TimeoutExpired("ffmpeg", recorder.X11GRAB_SETTLE_S)
    return proc


@pytest.fixture(autouse=True)
def display(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISPLAY", ":9")


@pytest.fixture
def make(tmp_path: Path) -> MakeRecorder:
    def build(backend: str = "x11grab", usable: frozenset[str] = frozenset({"libx264"})) -> recorder.Recorder:
        opts = RecorderOptions(
            session=SESSION, feedback=tmp_path, fps=30, audio="default", nice="0", usable=usable, backend=backend
        )
        return recorder.Recorder(alive(), recording_paths(tmp_path, SESSION), opts)

    return build


def test_an_off_recorder_does_nothing(make: MakeRecorder) -> None:
    rec = make()
    rec.off = True
    assert not rec.step()


def test_a_running_x11grab_part_keeps_going(make: MakeRecorder) -> None:
    rec = make()
    rec.proc = alive()
    assert rec.step()


def test_no_window_at_the_start_turns_recording_off(make: MakeRecorder, capsys: pytest.CaptureFixture[str]) -> None:
    rec = make()
    with mock.patch.object(window, "wait_stable", return_value=None):
        assert not rec.step()
    assert rec.off
    assert "no game window found" in capsys.readouterr().err


def test_a_window_that_never_returns_leaves_the_session_on(make: MakeRecorder) -> None:
    rec = make()
    rec.parts = [f"{SESSION}.mkv"]
    with mock.patch.object(window, "wait_stable", return_value=None):
        assert not rec.step()
    assert not rec.off


def test_a_found_window_starts_a_part(make: MakeRecorder, capsys: pytest.CaptureFixture[str]) -> None:
    rec = make()
    proc = running_ffmpeg()
    with (
        mock.patch.object(window, "wait_stable", return_value=WIN),
        mock.patch.object(procs, "spawn", return_value=proc) as spawn,
    ):
        assert rec.step()
    argv = spawn.call_args.args[0]
    assert Path(argv[0]).name == "nice"
    assert argv[1:3] == ["-n", "0"]
    assert spawn.call_args.kwargs["detach"] is True
    proc.wait.assert_called_once_with(timeout=recorder.X11GRAB_SETTLE_S)
    assert rec.parts == [f"{SESSION}.mkv"]
    assert "recording 1280x800 with libx264" in capsys.readouterr().err


def test_a_later_x11grab_part_keeps_the_first_parts_t0(make: MakeRecorder) -> None:
    rec = make()
    rec.parts, rec.t0 = [f"{SESSION}.mkv"], 123.0
    with mock.patch.object(procs, "spawn", return_value=running_ffmpeg()):
        rec._start_part(WIN)
    assert (rec.t0, rec.parts) == (123.0, [f"{SESSION}.mkv", f"{SESSION}.part2.mkv"])


def test_no_usable_encoder_stops_recording_with_a_message(
    make: MakeRecorder, capsys: pytest.CaptureFixture[str]
) -> None:
    rec = make(usable=frozenset())
    with mock.patch.object(window, "wait_stable", return_value=WIN):
        assert not rec.step()
    assert rec.off
    assert "not recording: neither h264_nvenc nor libx264" in capsys.readouterr().err


def test_a_program_that_cannot_start_stops_recording(make: MakeRecorder, capsys: pytest.CaptureFixture[str]) -> None:
    rec = make()
    with (
        mock.patch.object(window, "wait_stable", return_value=WIN),
        mock.patch.object(procs, "spawn", side_effect=FileNotFoundError("ffmpeg")),
    ):
        assert not rec.step()
    assert rec.off
    assert "not recording: ffmpeg" in capsys.readouterr().err


def test_an_ffmpeg_that_dies_at_start_is_retried_then_given_up_on(
    make: MakeRecorder, capsys: pytest.CaptureFixture[str]
) -> None:
    rec = make()
    with mock.patch.object(procs, "spawn", return_value=mock.Mock()):
        for attempt in range(1, recorder.MAX_QUICK_DEATHS + 1):
            rec._start_part(WIN)
            assert (rec.proc, rec.parts, rec.quick_deaths) == (None, [], attempt)
            assert rec.off == (attempt == recorder.MAX_QUICK_DEATHS)
    assert "ffmpeg died at start" in capsys.readouterr().err


def test_a_dead_window_part_is_replaced_by_waiting_for_the_next(
    make: MakeRecorder, capsys: pytest.CaptureFixture[str]
) -> None:
    rec = make()
    rec.parts = [f"{SESSION}.mkv"]
    rec.proc = mock.Mock(poll=mock.Mock(return_value=0))
    with mock.patch.object(window, "wait_stable", return_value=None):
        assert not rec.step()
    assert proc_of(rec) is None
    assert "the window went away" in capsys.readouterr().err


def test_a_gsr_part_whose_window_changed_is_stopped(make: MakeRecorder) -> None:
    rec = make("gsr")
    rec.proc = alive()
    rec.win = WIN
    rec.gsr.open_part = (Path(f"{SESSION}.mkv"), 1.0)
    with (
        mock.patch.object(window, "largest", return_value=OTHER),
        mock.patch.object(recorder, "stop_recorder", return_value=True) as stopped,
        mock.patch.object(window, "wait_stable", return_value=None),
    ):
        assert not rec.step()
    stopped.assert_called_once()
    assert open_part_of(rec) is None
    assert len(rec.gsr.pending) == 1


def test_a_recorder_that_died_is_not_recording(make: MakeRecorder) -> None:
    rec = make()
    rec.proc = mock.Mock(poll=mock.Mock(return_value=1))
    assert not rec._still_recording()


def test_without_an_open_gsr_part_nothing_is_counted(make: MakeRecorder) -> None:
    rec = make("gsr")
    rec._count_short_life()
    assert rec.gsr.short_lives == 0


def test_short_lived_gsr_parts_switch_the_session_to_x11grab(
    make: MakeRecorder, capsys: pytest.CaptureFixture[str]
) -> None:
    rec = make("gsr")
    rec.gsr.open_part = (Path(f"{SESSION}.mkv"), 1.0)
    with mock.patch.object(recorder, "time", SimpleNamespace(monotonic=lambda: 100.0)):
        rec.gsr.started = 99.0
        for _ in range(recorder.MAX_QUICK_DEATHS):
            assert rec.backend == "gsr"
            rec._count_short_life()
    assert rec.backend == "x11grab"
    assert "keeps stopping" in capsys.readouterr().err


def test_a_long_gsr_part_resets_the_count(make: MakeRecorder) -> None:
    rec = make("gsr")
    rec.gsr.open_part = (Path(f"{SESSION}.mkv"), 1.0)
    rec.gsr.short_lives = 2
    with mock.patch.object(recorder, "time", SimpleNamespace(monotonic=lambda: 100.0)):
        rec.gsr.started = 100.0 - recorder.SHORT_LIFE_S
        rec._count_short_life()
    assert (rec.gsr.short_lives, rec.backend) == (0, "gsr")


def test_an_alignment_that_fails_is_reported_not_raised(make: MakeRecorder, capsys: pytest.CaptureFixture[str]) -> None:
    rec = make("gsr")
    rec.gsr.pending = [(Path(f"/v/{SESSION}.part2.mkv"), 5.0)]
    with mock.patch.object(gsr, "align", side_effect=OSError("disk full")):
        rec._align_pending()
    assert f"could not align {SESSION}.part2.mkv to the timeline: disk full" in capsys.readouterr().err
    assert rec.gsr.pending == []


@pytest.mark.parametrize(("finalized", "said"), [(False, "ignored SIGINT"), (True, "")])
def test_stop_says_so_only_when_the_recorder_had_to_be_killed(
    make: MakeRecorder, capsys: pytest.CaptureFixture[str], *, finalized: bool, said: str
) -> None:
    rec = make("gsr")
    rec.proc = mock.Mock()
    with mock.patch.object(recorder, "stop_recorder", return_value=finalized):
        rec.stop()
    err = capsys.readouterr().err
    assert (said in err) if said else err == ""


def test_nothing_running_stops_quietly(make: MakeRecorder, capsys: pytest.CaptureFixture[str]) -> None:
    make("gsr").stop()
    assert capsys.readouterr().err == ""
