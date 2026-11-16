# Copyright (c) 2026 Krzysztof Rudnicki
"""supervise.run on the recording path: a real child game, the recorder and encoder probe faked."""

import re
import signal
import subprocess
import sys
import time
from typing import TYPE_CHECKING, Any, ClassVar
from unittest import mock

import pytest

from game_recording import encoder, finalize, gsr, procs, supervise, timeline
from game_recording.options import RecorderOptions, RunOptions
from game_recording.tests.test_helpers import CONFIG, SESSION

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

REAL_SLEEP = time.sleep


def game(seconds: float, code: int = 0) -> list[str]:
    return [sys.executable, "-c", f"import sys, time; time.sleep({seconds}); sys.exit({code})", "--dev"]


class FakeRecorder:
    """Stands in for Recorder: records what the launcher asked of it."""

    instances: ClassVar[list[FakeRecorder]] = []
    gives_up: ClassVar[bool] = False

    def __init__(self, game: object, paths: dict[str, Path], opts: RecorderOptions) -> None:
        self.paths = paths
        self.opts = opts
        self.off = FakeRecorder.gives_up
        self.steps = 0
        self.stopped = False
        FakeRecorder.instances.append(self)

    def step(self) -> bool:
        self.steps += 1
        return True

    def stop(self) -> None:
        self.stopped = True


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, str]]:
    FakeRecorder.instances = []
    FakeRecorder.gives_up = False
    saved = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
    monkeypatch.setattr(supervise, "Recorder", FakeRecorder)
    monkeypatch.setattr(encoder, "probe_usable", lambda: {"libx264"})
    monkeypatch.setattr(gsr, "available", lambda: False)
    monkeypatch.setattr(time, "sleep", lambda _s: REAL_SLEEP(0.02))
    yield {"DISPLAY": ":9", "HOME": "/nonexistent", "DEMO_BINARIES": str(tmp_path)}
    for sig, handler in saved.items():
        signal.signal(sig, handler)


def no_finish(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Path]]:
    calls: list[dict[str, Path]] = []
    monkeypatch.setattr(supervise, "_finish", lambda paths, config: calls.append(paths))
    return calls


def test_a_recorded_run_steps_the_recorder_and_returns_the_games_exit_code(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    finished = no_finish(monkeypatch)
    code = supervise.run(game(0.3, 5), CONFIG, RunOptions(force=True, session=SESSION, fps=60), env)
    assert code == 5
    rec = FakeRecorder.instances[0]
    assert rec.stopped
    assert rec.steps > 0
    assert (rec.opts.usable, rec.opts.backend, rec.opts.fps, rec.opts.session) == (
        frozenset({"libx264"}),
        "x11grab",
        60,
        SESSION,
    )
    assert rec.opts.nice == "10"
    assert rec.paths["meta"].name == f"{SESSION}.rec.json"
    assert finished == [rec.paths]


def test_the_recorder_nice_value_comes_from_the_given_env(env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    no_finish(monkeypatch)
    supervise.run(game(0.1), CONFIG, RunOptions(force=True), {**env, "DEMO_RECORDER_NICE": "0"})
    assert FakeRecorder.instances[0].opts.nice == "0"


def test_the_game_gets_a_session_and_feedback_dir_in_its_args(
    env: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    no_finish(monkeypatch)
    spawned: list[list[str]] = []
    real_spawn = procs.spawn

    def spy(argv: list[str], *, env: dict[str, str]) -> subprocess.Popen[bytes]:
        spawned.append(list(argv))
        child: subprocess.Popen[bytes] = real_spawn(argv, env=env)
        return child

    monkeypatch.setattr(procs, "spawn", spy)
    supervise.run(game(0.1), CONFIG, RunOptions(force=True), env)
    argv = spawned[0]
    assert argv[-2] == f"--session-id={supervise.session_of(argv)}"
    assert argv[-1] == f"--feedback-dir={tmp_path}/feedback"
    assert re.fullmatch(r"\d+-run-[0-9a-f]{4}", supervise.session_of(argv))


def test_max_seconds_stops_the_game_once_recording_began(env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    no_finish(monkeypatch)
    options = RunOptions(force=True, session=SESSION, max_seconds=0.1)
    assert supervise.run(game(30), CONFIG, options, env) == -signal.SIGTERM


def test_a_recorder_that_gave_up_still_starts_the_timer(env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    no_finish(monkeypatch)
    FakeRecorder.gives_up = True
    monkeypatch.setattr(FakeRecorder, "step", lambda _self: False)
    options = RunOptions(force=True, session=SESSION, max_seconds=0.1)
    assert supervise.run(game(30), CONFIG, options, env) == -signal.SIGTERM


def test_the_timer_waits_while_the_recorder_is_still_starting(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    no_finish(monkeypatch)
    steps = iter([False, False, True])
    monkeypatch.setattr(FakeRecorder, "step", lambda _self: next(steps, True))
    options = RunOptions(force=True, session=SESSION, max_seconds=0.1)
    assert supervise.run(game(30), CONFIG, options, env) == -signal.SIGTERM


def test_a_blocked_run_says_why_it_is_not_recorded(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    FakeRecorder.instances = []
    monkeypatch.setattr(supervise, "Recorder", FakeRecorder)
    code = supervise.run([sys.executable, "-c", "pass"], CONFIG, env={"DISPLAY": ":9", "DEMO_NO_RECORD": "1"})
    assert code == 0
    assert "off (DEMO_NO_RECORD=1)" in capsys.readouterr().err
    assert not FakeRecorder.instances


def test_a_forwarded_hangup_reaches_the_game() -> None:
    saved = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
    try:
        proc = mock.Mock()
        supervise._forward_signals(proc)
        handler = signal.getsignal(signal.SIGHUP)
        assert callable(handler)
        handler(signal.SIGHUP, None)
        proc.send_signal.assert_called_once_with(signal.SIGHUP)
        assert signal.getsignal(signal.SIGINT) == signal.SIG_IGN
    finally:
        for sig, handler in saved.items():
            signal.signal(sig, handler)


def doc(parts: int) -> dict[str, Any]:
    events = [{"t": 1.0}, {"t": 2.0, "before_recording": True}]
    video = {"file": f"{SESSION}.mkv", "duration_s": 61.4, "parts": [{}] * parts}
    return {"events": events, "video": video}


@pytest.fixture
def meta_paths(tmp_path: Path) -> dict[str, Path]:
    paths = supervise.recording_paths(tmp_path, SESSION)
    paths["dir"].mkdir(parents=True)
    paths["meta"].write_text("{}")
    return paths


def test_without_a_rec_json_there_is_nothing_to_finish(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    supervise._finish(supervise.recording_paths(tmp_path, SESSION), CONFIG)
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize(("parts", "tail"), [(1, "1 moments)"), (2, "1 moments, 2 parts)")])
def test_the_summary_line_counts_the_moments_inside_the_video(
    meta_paths: dict[str, Path],
    parts: int,
    tail: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(finalize, "finalize", lambda _meta, _map: doc(parts))
    supervise._finish(meta_paths, CONFIG)
    err = capsys.readouterr().err
    assert f"{SESSION}.mkv (61 s, {tail}" in err


@pytest.mark.parametrize(
    "error",
    [
        KeyError("video"),
        OSError("disk"),
        ValueError("bad json"),
        TypeError("shape"),
        subprocess.SubprocessError("ffmpeg"),
        timeline.NoSyncError("no sync"),
    ],
)
def test_a_finalize_error_is_reported_not_raised(
    meta_paths: dict[str, Path],
    error: Exception,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(_meta: Path, _map: object) -> None:
        raise error

    monkeypatch.setattr(finalize, "finalize", boom)
    supervise._finish(meta_paths, CONFIG)
    assert f"could not build the timeline: {error}" in capsys.readouterr().err


def test_an_unexpected_error_is_not_swallowed(meta_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_meta: Path, _map: object) -> None:
        msg = "bug"
        raise RuntimeError(msg)

    monkeypatch.setattr(finalize, "finalize", boom)
    with pytest.raises(RuntimeError, match="bug"):
        supervise._finish(meta_paths, CONFIG)
