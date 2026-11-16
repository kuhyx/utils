# Copyright (c) 2026 Krzysztof Rudnicki
"""gpu-screen-recorder: starting it, and moving a finished part onto the timeline."""

from itertools import pairwise
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from game_recording import encoder, gsr

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


def install_fake(folder: Path) -> None:
    path = folder / "gpu-screen-recorder"
    path.write_text(FAKE_GSR.format(python=sys.executable), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, wait_s: float = 5.0
) -> tuple[subprocess.Popen[bytes], float] | None:
    install_fake(tmp_path)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_GSR", mode)
    spec = encoder.Spec(window_id=1, fps=30, t0_unix=0.0, out=str(tmp_path / "s.mkv"))
    with (tmp_path / "log").open("ab") as log:
        return gsr.start(spec, log, "0", wait_s=wait_s)


def test_available_follows_the_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    assert not gsr.available()
    install_fake(tmp_path)
    assert gsr.available()


def test_returns_the_running_recorder_and_its_first_frame_unix_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = _start(tmp_path, monkeypatch, "ok")
    assert started is not None
    proc, first = started
    try:
        assert proc.poll() is None
        # gsr stamps its first frame after the screen showed it (measured on :0, bench.sh sync)
        assert first == pytest.approx(1_800_000_007.25 - gsr.CAPTURE_LATENCY_S, abs=1e-6)
    finally:
        proc.kill()
        proc.wait()


def test_a_recorder_that_dies_at_start_is_a_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _start(tmp_path, monkeypatch, "die") is None


def test_a_recorder_that_never_stamps_its_first_frame_is_killed_and_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _start(tmp_path, monkeypatch, "nots", wait_s=1.0) is None
    assert not (tmp_path / "s.mkv.ts").exists()


def test_delta_puts_the_first_frame_on_the_t0_timeline() -> None:
    assert gsr.shift_delta(first_unix=107.0, t0=100.0, first_stamp=0.0) == pytest.approx(7.0)
    assert gsr.shift_delta(first_unix=107.0, t0=100.0, first_stamp=0.25) == pytest.approx(6.75)


def test_shift_command_copies_streams_and_moves_the_stamps() -> None:
    cmd = gsr.shift_command(Path("/o/a.mkv"), Path("/o/a.shift.mkv"), 7.0)
    pairs = list(pairwise(cmd))
    assert ("-output_ts_offset", "7.000000") in pairs
    assert ("-c", "copy") in pairs
    assert "-copyts" in cmd
    assert cmd[-1] == "/o/a.shift.mkv"


def test_align_moves_a_real_file_onto_the_timeline(tmp_path: Path) -> None:
    video = tmp_path / "p.mkv"
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=30", "-t", "1"]
    subprocess.run([*cmd, "-c:v", "libx264", str(video)], check=True, timeout=30)
    assert gsr.video_start(video) == pytest.approx(0.0, abs=1e-3)
    gsr.align(video, first_unix=107.0, t0=100.0)
    assert gsr.video_start(video) == pytest.approx(7.0, abs=1e-2)
    assert [p.name for p in tmp_path.iterdir()] == ["p.mkv"]


def test_a_file_already_on_the_timeline_is_left_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    video = tmp_path / "p.mkv"
    video.write_bytes(b"not a video")  # would make ffprobe/ffmpeg fail if touched
    monkeypatch.setattr(gsr, "video_start", lambda _video: 0.0005)
    gsr.align(video, first_unix=100.0, t0=100.0)
    assert video.read_bytes() == b"not a video"
