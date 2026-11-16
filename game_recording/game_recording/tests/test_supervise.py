# Copyright (c) 2026 Krzysztof Rudnicki
"""Launcher logic: session ids, folders, a recorder that finalizes on exit, process helpers."""

from pathlib import Path
import signal
import subprocess
import sys
import textwrap
import time
from unittest import mock

import pytest

from game_recording import procs, supervise
from game_recording.recorder import stop_recorder
from game_recording.tests.test_helpers import CONFIG


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (["godot", "--path", "/r", "--", "--dev"], ["godot", "--path", "/r", "--", "--dev", "--session-id=s1"]),
        (["/b/game"], ["/b/game", "--", "--session-id=s1"]),
    ],
)
def test_session_id_is_added_after_the_double_dash(command: list[str], expected: list[str]) -> None:
    assert supervise.with_session(command, "s1") == expected


def test_an_existing_session_id_wins() -> None:
    cmd = ["godot", "--", "--dev", "--session-id=mine"]
    assert supervise.with_session(cmd, "s1") == cmd
    assert supervise.session_of(cmd) == "mine"
    assert supervise.session_of(["godot"]) == ""


def test_feedback_dir_comes_from_the_args_then_the_binaries_dir() -> None:
    assert supervise.feedback_dir(["g", "--", "--feedback-dir=/fb"], {}, CONFIG) == Path("/fb")
    assert supervise.feedback_dir(["g", "--", "--dev"], {"DEMO_BINARIES": "/bin"}, CONFIG) == Path("/bin/feedback")
    assert supervise.feedback_dir(["g"], {"HOME": "/h"}, CONFIG) == Path("/h/data/demo_binaries/feedback")


def test_feedback_dir_without_home_falls_back_to_the_users_home() -> None:
    assert supervise.feedback_dir(["g"], {}, CONFIG) == Path.home() / "data/demo_binaries/feedback"


def test_recordings_land_next_to_the_feedback_log() -> None:
    paths = supervise.recording_paths(Path("/fb"), "s1")
    assert paths["video"] == Path("/fb/recordings/s1.mkv")
    assert paths["events"] == Path("/fb/recordings/s1.events.json")
    assert paths["meta"] == Path("/fb/recordings/s1.rec.json")
    assert paths["log"] == Path("/fb/recordings/s1.ffmpeg.log")


def test_a_new_session_id_is_a_timestamp_and_four_hex_digits() -> None:
    assert supervise.new_session().count("-run-") == 1
    assert supervise.new_session().split("-run-")[1].isalnum()
    assert len(supervise.new_session().rsplit("-", 1)[1]) == 4


def test_the_recorder_nice_comes_from_the_environment() -> None:
    assert supervise._nice({}, CONFIG) == "10"
    assert supervise._nice({"DEMO_RECORDER_NICE": "0"}, CONFIG) == "0"


def fake_recorder(tmp_path: Path, *, handle_sigint: bool) -> subprocess.Popen[bytes]:
    done = tmp_path / "finalized"
    body = f"""
        import signal, sys, time, pathlib
        def stop(*_):
            pathlib.Path({str(done)!r}).write_text("trailer written")
            sys.exit(0)
        signal.signal(signal.SIGINT, {"stop" if handle_sigint else "signal.SIG_IGN"})
        print("up", flush=True)
        time.sleep(60)
    """
    proc = subprocess.Popen([sys.executable, "-c", textwrap.dedent(body)], stdout=subprocess.PIPE)
    assert proc.stdout is not None
    proc.stdout.readline()  # wait until the handlers are installed
    return proc


def test_sigint_lets_the_recorder_finalize_its_file(tmp_path: Path) -> None:
    proc = fake_recorder(tmp_path, handle_sigint=True)
    with proc:
        assert stop_recorder(proc, grace_s=5.0)
        assert (tmp_path / "finalized").read_text() == "trailer written"
        assert proc.poll() is not None


def test_a_recorder_that_ignores_sigint_is_killed_after_the_grace(tmp_path: Path) -> None:
    proc = fake_recorder(tmp_path, handle_sigint=False)
    with proc:
        started = time.monotonic()
        assert not stop_recorder(proc, grace_s=0.5)
        assert time.monotonic() - started < 5.0
        assert proc.poll() is not None


def test_a_recorder_that_already_exited_is_fine() -> None:
    with subprocess.Popen([sys.executable, "-c", "pass"]) as proc:
        proc.wait()
        assert stop_recorder(proc, grace_s=1.0)


def test_a_blocked_run_just_runs_the_command_and_keeps_its_exit_code() -> None:
    env = {"DISPLAY": ":0"}
    code = supervise.run([sys.executable, "-c", "import sys; sys.exit(7)", "--autodrive"], CONFIG, env=env)
    assert code == 7


def test_run_defaults_to_the_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISPLAY", raising=False)
    assert supervise.run([sys.executable, "-c", "import sys; sys.exit(3)"], CONFIG) == 3


def test_stop_game_terminates_a_running_game_only() -> None:
    running = mock.Mock()
    running.poll.return_value = None
    supervise._stop_game(running)
    running.send_signal.assert_called_once_with(signal.SIGTERM)
    done = mock.Mock()
    done.poll.return_value = 0
    supervise._stop_game(done)
    done.send_signal.assert_not_called()


def test_program_resolves_a_path_or_keeps_the_bare_name() -> None:
    assert Path(procs.program("sh")).is_absolute()
    assert procs.program("no-such-program-xyz") == "no-such-program-xyz"


def test_niced_puts_the_command_under_nice() -> None:
    argv = procs.niced("7", ["ffmpeg", "-i", "x"])
    assert Path(argv[0]).name == "nice"
    assert argv[1:] == ["-n", "7", "ffmpeg", "-i", "x"]


def test_spawn_passes_the_environment_log_and_session(tmp_path: Path) -> None:
    out = tmp_path / "out.log"
    with out.open("wb") as log:
        child = procs.spawn(
            [sys.executable, "-c", "import os; print(os.environ['SPAWN_X'], os.getsid(0) == os.getpid())"],
            env={"SPAWN_X": "yes"},
            log=log,
            detach=True,
        )
        assert child.wait() == 0
    assert out.read_text().split() == ["yes", "True"]


def test_spawn_without_an_environment_inherits_ours() -> None:
    assert procs.spawn([sys.executable, "-c", "pass"]).wait() == 0
