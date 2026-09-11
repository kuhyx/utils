# Copyright (c) 2026 Krzysztof Rudnicki
"""WAV: write what was rendered so a person can hear it, and fingerprint it.

16-bit mono PCM is what Godot's ``AudioStreamWAV`` and ``aplay`` both take
without conversion. The SHA-256 is what a manifest records so a re-render
can prove it reproduced the committed file byte for byte.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING
import wave

import numpy as np

from music_theory import synth

if TYPE_CHECKING:
    from pathlib import Path

_BYTES_PER_SAMPLE = 2
_CHANNELS = 1


def write(
    path: Path, signal: synth.Signal, sample_rate: int = synth.SAMPLE_RATE
) -> Path:
    """Write a float signal as 16-bit mono PCM and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.Wave_write(str(path)) as handle:
        handle.setnchannels(_CHANNELS)
        handle.setsampwidth(_BYTES_PER_SAMPLE)
        handle.setframerate(sample_rate)
        handle.writeframes(synth.to_int16(signal).tobytes())
    return path


def read(path: Path) -> tuple[synth.Signal, int]:
    """Read a 16-bit mono WAV back into a float signal and its sample rate."""
    with wave.Wave_read(str(path)) as handle:
        if (
            handle.getsampwidth() != _BYTES_PER_SAMPLE
            or handle.getnchannels() != _CHANNELS
        ):
            msg = f"{path} is not 16-bit mono"
            raise ValueError(msg)
        rate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32767.0
    return samples, rate


def sha256(path: Path) -> str:
    """Hex digest of the file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def duration_seconds(
    signal: synth.Signal, sample_rate: int = synth.SAMPLE_RATE
) -> float:
    """Length of a signal in seconds."""
    return len(signal) / sample_rate


def play_command(path: Path) -> str:
    """The one line a person runs to hear the file."""
    return f"aplay -q {path}"
