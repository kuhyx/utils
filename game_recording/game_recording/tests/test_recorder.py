# Copyright (c) 2026 Krzysztof Rudnicki
"""The launcher's Recorder: backend choice, fallback to x11grab, the t0 of a gsr part, 30 fps."""

from collections.abc import Callable, Iterator
import json
import os
import signal
import stat
import sys
import time
from typing import TYPE_CHECKING
from unittest import mock

import pytest

from game_recording import gsr, procs, recorder, window
from game_recording.options import DEFAULT_FPS, RecorderOptions
from game_recording.supervise import recording_paths

FAKE_GSR = """#!{python}
import os, pathlib, signal, sys, time
args = sys.argv[1:]
out = args[args.index("-o") + 1]
mode = os.environ.get("FAKE_GSR", "ok")
if mode == "die":
    sys.exit(1)
if mode == "ok":
    pathlib.Path(out + ".ts").write_text("monotonic_microsec\\trealtime_microsec\\n5\\t1800000007250000\\n")
signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
time.sleep(60)
"""
FAKE_FFMPEG = """#!{python}
import signal, sys, time
signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
time.sleep(60)
"""
if TYPE_CHECKING:
    from pathlib import Path

WIN = window.Window(id=0x4200007, width=1280, height=800)
GSR_T0 = 1_800_000_007.25 - gsr.CAPTURE_LATENCY_S  # FAKE_GSR's first-frame stamp, less the latency

Make = Callable[[str], recorder.Recorder]


def install_fake(folder: Path, name: str, body: str) -> None:
    path = folder / name
    path.write_text(body.format(python=sys.executable), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class Rig:
    """A recorder factory over fake gsr and ffmpeg binaries; every recorder it made is stopped at the end."""

    def __init__(self, root: Path) -> None:
        self.feedback = root / "fb"
        self.paths = recording_paths(self.feedback, "s1")
        self.made: list[recorder.Recorder] = []

    def make(self, backend: str) -> recorder.Recorder:
        opts = RecorderOptions(
            session="s1", feedback=self.feedback, fps=30, audio="default", nice="0",
            usable=frozenset({"libx264"}), backend=backend,
        )  # fmt: skip
        rec = recorder.Recorder(mock.Mock(), self.paths, opts)
        self.made.append(rec)
        return rec

    def meta(self) -> dict[str, object]:
        data: dict[str, object] = json.loads(self.paths["meta"].read_text(encoding="utf-8"))
        return data

    def running_gsr(self) -> recorder.Recorder:
        rec = self.make("gsr")
        rec._start_part(WIN)
        return rec


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    install_fake(bin_dir, "gpu-screen-recorder", FAKE_GSR)
    install_fake(bin_dir, "ffmpeg", FAKE_FFMPEG)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("DISPLAY", ":9")
    monkeypatch.setenv("FAKE_GSR", "ok")
    made = Rig(tmp_path)
    yield made
    for rec in made.made:
        if rec.proc is not None and rec.proc.poll() is None:
            rec.proc.send_signal(signal.SIGKILL)
            rec.proc.wait()


def stop_quietly(rec: recorder.Recorder) -> None:
    """Stops the recorder with the alignment (ffprobe on a fake file) faked out."""
    with mock.patch.object(gsr, "align"):
        rec.stop()


def test_defaults_are_30_fps() -> None:
    assert DEFAULT_FPS == 30


def test_gsr_part_puts_t0_on_its_first_frame(rig: Rig) -> None:
    rec = rig.running_gsr()
    stop_quietly(rec)
    assert rec.backend == "gsr"
    assert rec.t0 == pytest.approx(GSR_T0, abs=1e-6)
    meta = rig.meta()
    assert meta["t0_unix"] == pytest.approx(GSR_T0, abs=1e-6)
    assert meta["backend"] == "gsr"
    assert meta["parts"] == ["s1.mkv"]
    assert meta["fps"] == 30


def test_a_gsr_that_fails_at_start_falls_back_to_x11grab_with_a_fresh_t0(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_GSR", "die")
    rec = rig.make("gsr")
    before = time.time()
    rec._start_part(WIN)
    stop_quietly(rec)
    assert rec.backend == "x11grab"
    assert rec.t0 >= before
    assert rec.t0 < time.time() + 1
    meta = rig.meta()
    assert meta["backend"] == "x11grab"
    assert meta["parts"] == ["s1.mkv"]


def test_gsr_keeps_recording_while_its_window_is_shown(rig: Rig) -> None:
    rec = rig.running_gsr()
    proc = rec.proc
    with mock.patch.object(window, "largest", return_value=WIN):
        assert rec.step()
    assert rec.proc is proc
    stop_quietly(rec)


def test_gsr_part_ends_when_its_window_is_hidden_so_a_new_part_follows(rig: Rig) -> None:
    # gsr neither exits nor resumes after an unmap (bench.sh gap on :0): the recorder ends the part itself
    rec = rig.running_gsr()
    proc = rec.proc
    assert proc is not None
    with (
        mock.patch.object(window, "largest", return_value=None),
        mock.patch.object(window, "wait_stable", return_value=None),
    ):
        assert not rec.step()
    assert proc.poll() is not None, "the hidden window's gsr was stopped"
    assert rec.proc is None
    assert len(rec.gsr.pending) == 1
    stop_quietly(rec)


def test_x11grab_backend_never_starts_gsr(rig: Rig) -> None:
    rec = rig.make("x11grab")
    with mock.patch.object(gsr, "start") as started:
        rec._start_part(WIN)
    started.assert_not_called()
    assert rig.meta()["backend"] == "x11grab"
    stop_quietly(rec)


def test_stopping_a_gsr_part_aligns_a_later_part_to_the_t0_timeline(rig: Rig) -> None:
    rec = rig.make("gsr")
    rec.t0 = GSR_T0 - 10.0
    rec.parts = ["s1.mkv"]  # a second part: its first frame is 10 s after t0
    with mock.patch.object(gsr, "align") as align:
        rec._start_part(WIN)
        rec.stop()
    align.assert_called_once_with(rig.paths["dir"] / "s1.part2.mkv", first_unix=GSR_T0, t0=GSR_T0 - 10.0)
    assert rec.t0 == GSR_T0 - 10.0


def test_a_part_that_ended_during_play_is_aligned_only_after_the_game_exits(rig: Rig) -> None:
    rec = rig.make("gsr")
    with mock.patch.object(gsr, "align") as align:
        rec._start_part(WIN)
        assert rec.proc is not None
        rec.proc.send_signal(signal.SIGINT)
        rec.proc.wait(timeout=5)
        rec.close_part()  # the window went away; the game still runs
        align.assert_not_called()
        rec.stop()  # the game exited
    align.assert_called_once()


def test_every_pending_part_is_aligned_once_and_its_first_frame_is_in_rec_json(rig: Rig) -> None:
    rec = rig.make("gsr")
    with mock.patch.object(gsr, "align") as align:
        for _ in range(2):
            rec._start_part(WIN)
            assert rec.proc is not None
            rec.proc.send_signal(signal.SIGINT)
            rec.proc.wait(timeout=5)
            rec.close_part()
        rec.stop()
    assert align.call_count == 2
    assert rig.meta()["first_frame_unix"] == {"s1.mkv": GSR_T0, "s1.part2.mkv": GSR_T0}


def test_a_dead_proc_still_closes_once(rig: Rig) -> None:
    rec = rig.make("gsr")
    with mock.patch.object(gsr, "align") as align:
        rec._start_part(WIN)
        rec.stop()
        rec.stop()
    assert align.call_count == 1


def test_stop_recorder_returns_true_for_an_already_ended_process() -> None:
    done = procs.spawn([sys.executable, "-c", "pass"])
    done.wait(timeout=20)
    assert recorder.stop_recorder(done)


def test_stop_recorder_interrupts_a_running_process_and_reports_a_clean_finish() -> None:
    code = "import signal, sys, time; signal.signal(signal.SIGINT, lambda *_: sys.exit(0)); time.sleep(60)"
    proc = procs.spawn([sys.executable, "-c", code])
    time.sleep(0.5)  # let the child install its handler
    assert recorder.stop_recorder(proc, grace_s=10.0)
    assert proc.returncode == 0


def test_stop_recorder_kills_a_process_that_ignores_sigint() -> None:
    code = "import signal, time; signal.signal(signal.SIGINT, signal.SIG_IGN); time.sleep(60)"
    proc = procs.spawn([sys.executable, "-c", code])
    time.sleep(0.5)
    assert not recorder.stop_recorder(proc, grace_s=0.2)
    assert proc.returncode == -signal.SIGKILL
