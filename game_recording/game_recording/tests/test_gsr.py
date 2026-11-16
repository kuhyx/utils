# Copyright (c) 2026 Krzysztof Rudnicki
"""gpu-screen-recorder backend: argv, backend choice, first-frame time."""

from itertools import pairwise
from pathlib import Path

import pytest

from game_recording import encoder, gsr
from game_recording.tests.test_helpers import CONFIG

SPEC = encoder.Spec(window_id=39845893, fps=30, t0_unix=1_800_000_000.5, out="/o/s.mkv", audio="default")
TS_TEXT = "monotonic_microsec\trealtime_microsec\n8935499369\t1794415951373572\n"
ENV_NAME = "DEMO_RECORDER_BACKEND"


def _pairs(spec: encoder.Spec = SPEC) -> list[tuple[str, str]]:
    return list(pairwise(gsr.command(spec)))


def test_records_the_window_on_the_gpu_at_the_fps() -> None:
    cmd = gsr.command(SPEC)
    assert cmd[0] == "gpu-screen-recorder"
    pairs = _pairs()
    for pair in (("-w", "39845893"), ("-f", "30"), ("-k", "h264"), ("-c", "mkv"), ("-o", "/o/s.mkv")):
        assert pair in pairs
    assert "x11grab" not in cmd


def test_the_first_frame_time_is_written_for_the_timeline() -> None:
    assert ("-write-first-frame-ts", "yes") in _pairs()


def test_constant_frame_rate_without_the_cursor_and_quiet() -> None:
    pairs = _pairs()
    for pair in (("-fm", "cfr"), ("-cursor", "no"), ("-v", "no"), ("-q", "very_high")):
        assert pair in pairs


def test_audio_is_the_default_output_as_opus_because_flac_is_disabled_in_gsr() -> None:
    pairs = _pairs()
    assert ("-a", "default_output") in pairs
    assert ("-ac", "opus") in pairs


def test_a_named_pulse_source_is_a_device() -> None:
    spec = encoder.Spec(window_id=1, fps=30, t0_unix=0.0, out="/o/s.mkv", audio="sink.monitor")
    assert ("-a", "device:sink.monitor") in _pairs(spec)


def test_ts_file_sits_next_to_the_video_with_an_extra_extension() -> None:
    assert gsr.ts_path("/o/s.mkv") == Path("/o/s.mkv.ts")


def test_the_realtime_column_is_the_unix_time() -> None:
    assert gsr.parse_first_frame(TS_TEXT) == pytest.approx(1794415951.373572, abs=1e-6)


@pytest.mark.parametrize(
    "text",
    ["", "monotonic_microsec\trealtime_microsec\n", TS_TEXT.rstrip("\n"), "x\ty\n1\t2z\n", "1\t2\t3\n"],
)
def test_a_missing_or_partial_file_is_not_a_time_yet(text: str) -> None:
    assert gsr.parse_first_frame(text) is None


def test_the_measured_capture_latency_is_between_two_and_three_frames_at_30_fps() -> None:
    assert 2 / 30 < gsr.CAPTURE_LATENCY_S < 3 / 30


@pytest.mark.parametrize(
    ("env", "audio", "want", "have_gsr"),
    [
        ({}, "default", "gsr", True),
        ({}, "default", "x11grab", False),
        ({ENV_NAME: "x11grab"}, "default", "x11grab", True),
        ({ENV_NAME: "gsr"}, "default", "gsr", True),
        ({}, "lavfi", "x11grab", True),
    ],
)
def test_backend_choice(env: dict[str, str], audio: str, want: str, *, have_gsr: bool) -> None:
    assert gsr.pick_backend(env, audio, CONFIG, have_gsr=have_gsr) == want


def test_the_env_name_comes_from_the_config_prefix() -> None:
    assert CONFIG.env_name(gsr.BACKEND_SUFFIX) == ENV_NAME
    assert gsr.pick_backend({"OTHER_RECORDER_BACKEND": "x11grab"}, "default", CONFIG, have_gsr=True) == "gsr"
