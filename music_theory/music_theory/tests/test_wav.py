# Copyright (c) 2026 Krzysztof Rudnicki
from typing import TYPE_CHECKING
import wave

import numpy as np
import pytest

from music_theory import synth, wav

if TYPE_CHECKING:
    from pathlib import Path


def test_write_and_read_round_trip(tmp_path: Path) -> None:
    signal = synth.oscillator(440.0, 0.1)
    path = wav.write(tmp_path / "sub" / "a.wav", signal, 8000)
    back, rate = wav.read(path)
    assert rate == 8000
    assert len(back) == len(signal)
    assert np.allclose(back, signal, atol=1e-3)


def test_read_rejects_stereo(tmp_path: Path) -> None:
    path = tmp_path / "stereo.wav"
    with wave.Wave_write(str(path)) as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\0\0\0\0")
    with pytest.raises(ValueError, match="16-bit mono"):
        wav.read(path)


def test_sha256_is_stable(tmp_path: Path) -> None:
    path = wav.write(tmp_path / "a.wav", np.zeros(10))
    assert wav.sha256(path) == wav.sha256(path)
    assert len(wav.sha256(path)) == 64


def test_duration_and_play_command(tmp_path: Path) -> None:
    assert wav.duration_seconds(np.zeros(22050)) == 1.0
    assert wav.play_command(tmp_path / "x.wav").startswith("aplay -q ")
