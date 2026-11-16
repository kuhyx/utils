# Copyright (c) 2026 Krzysztof Rudnicki
"""The ffmpeg command line: encoder choice, window capture, exact timestamps."""

from dataclasses import replace
from itertools import pairwise
import subprocess

import pytest

from game_recording import encoder

SPEC = encoder.Spec(window_id=0x4200007, fps=60, t0_unix=1_800_000_000.5, out="/o/s.mkv", audio="default")


def _pairs(cmd: list[str]) -> list[tuple[str, str]]:
    return list(pairwise(cmd))


def test_nvenc_is_preferred_when_it_works() -> None:
    assert encoder.pick({"h264_nvenc", "libx264"}) == "h264_nvenc"


def test_falls_back_to_x264() -> None:
    assert encoder.pick(["libx264"]) == "libx264"


def test_nothing_usable_is_an_error() -> None:
    with pytest.raises(encoder.NoEncoderError):
        encoder.pick({"mpeg4"})


def test_probe_lists_only_the_encoders_that_encode_a_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def run(cmd: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0 if "libx264" in cmd else 1)

    monkeypatch.setattr(subprocess, "run", run)
    assert encoder.probe_usable() == {"libx264"}
    assert len(calls) == 2


def test_nvenc_is_quality_first() -> None:
    pairs = _pairs(encoder.command(SPEC, "h264_nvenc"))
    for pair in (("-preset", "p7"), ("-rc", "vbr"), ("-cq", "17"), ("-b:v", "0")):
        assert pair in pairs


def test_4k_windows_use_a_faster_nvenc_preset_to_stay_real_time() -> None:
    big = replace(SPEC, width=3840, height=2160)
    assert ("-preset", "p4") in _pairs(encoder.command(big, "h264_nvenc"))
    qhd = replace(SPEC, width=2560, height=1440)
    assert ("-preset", "p7") in _pairs(encoder.command(qhd, "h264_nvenc"))


def test_x264_fallback_settings() -> None:
    pairs = _pairs(encoder.command(SPEC, "libx264"))
    assert ("-crf", "16") in pairs
    assert ("-preset", "veryfast") in pairs


def test_captures_the_window_by_id_at_the_fps() -> None:
    cmd = encoder.command(SPEC, "h264_nvenc")
    assert ("-window_id", "0x4200007") in _pairs(cmd)
    assert ("-framerate", "60") in _pairs(cmd)
    assert "x11grab" in cmd


def test_output_is_mkv_and_sits_on_the_launcher_clock() -> None:
    cmd = encoder.command(SPEC, "h264_nvenc")
    assert "-copyts" in cmd
    assert ("-output_ts_offset", "-1800000000.500000") in _pairs(cmd)
    assert cmd[-1] == "/o/s.mkv"
    assert ("-f", "matroska") in _pairs(cmd)


def test_video_stamps_are_shifted_back_by_the_grab_latency() -> None:
    cmd = encoder.command(SPEC, "h264_nvenc")
    assert ("-itsoffset", "-0.025000") in _pairs(cmd)  # 1.5 frames at 60 fps
    assert cmd.index("-itsoffset") < cmd.index("x11grab"), "an input option of the video input"


def test_ffmpeg_ends_when_the_window_capture_dies() -> None:
    assert "-shortest" in encoder.command(SPEC, "h264_nvenc")


def test_audio_is_recorded_not_muted() -> None:
    cmd = encoder.command(SPEC, "h264_nvenc")
    assert "pulse" in cmd
    assert ("-c:a", "flac") in _pairs(cmd)
    assert ("-i", encoder.DEFAULT_MONITOR) in _pairs(cmd)


def test_pulse_source_is_the_given_monitor() -> None:
    cmd = encoder.command(replace(SPEC, audio="sink.monitor"), "h264_nvenc")
    assert ("-i", "sink.monitor") in _pairs(cmd)


def test_silent_test_source_rides_the_wall_clock() -> None:
    cmd = encoder.command(replace(SPEC, audio="lavfi"), "h264_nvenc")
    assert "lavfi" in cmd
    assert any("RTCTIME" in part for part in cmd)


def test_odd_window_sizes_are_cropped_to_even() -> None:
    assert "-vf" in encoder.command(replace(SPEC, width=1281, height=800), "h264_nvenc")
    assert "-vf" in encoder.command(replace(SPEC, width=1280, height=801), "h264_nvenc")
    assert "-vf" not in encoder.command(replace(SPEC, width=1280, height=800), "h264_nvenc")


def test_no_resize_scaler_in_the_path() -> None:
    assert "-vf" not in encoder.command(SPEC, "h264_nvenc")
