# Copyright (c) 2026 Krzysztof Rudnicki
"""Synth: turn frequencies into samples, with envelopes and timbre.

Article sections 1 and 2. A sound is a number changing over time; an
envelope shapes its volume so a note has a beginning and an end (and no
click), and timbre is the recipe of overtones -- sine, triangle, square and
saw are four such recipes at the same pitch.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

import numpy as np
import numpy.typing as npt

type Signal = npt.NDArray[np.float64]
type Waveform = Literal["sine", "triangle", "square", "saw"]

## The game's engine bands are 22050 Hz mono; keeping the same rate means a
## bed and the engine never need resampling against each other.
SAMPLE_RATE = 22050

## Headroom so summed voices and the game's other sounds have room to breathe.
DEFAULT_PEAK = 0.8

WAVEFORMS: tuple[Waveform, ...] = ("sine", "triangle", "square", "saw")

_INT16_FULL_SCALE = 32767.0

## A square wave is high for the first half of each cycle.
_HALF_CYCLE = 0.5


@dataclass(frozen=True)
class Envelope:
    """ADSR volume curve. Times in seconds, sustain as a 0..1 level.

    A 10 ms attack reads as struck, 500 ms as bowed; the release is what
    stops a note ending in a click.
    """

    attack: float = 0.01
    decay: float = 0.05
    sustain: float = 0.8
    release: float = 0.05


## Shared default so dataclass fields and argument defaults never call a
## constructor at import time (ruff B008/RUF009).
DEFAULT_ENVELOPE = Envelope()


def time_axis(seconds: float, sample_rate: int = SAMPLE_RATE) -> Signal:
    """Sample times for a duration, starting at 0."""
    frames = max(int(seconds * sample_rate), 0)
    return np.arange(frames, dtype=np.float64) / sample_rate


def oscillator(
    hz: float,
    seconds: float,
    waveform: Waveform = "sine",
    sample_rate: int = SAMPLE_RATE,
) -> Signal:
    """One waveform at one frequency, amplitude 1, no envelope."""
    if waveform not in WAVEFORMS:
        msg = f"unknown waveform {waveform!r}; choose one of {WAVEFORMS}"
        raise ValueError(msg)
    phase = (time_axis(seconds, sample_rate) * hz) % 1.0
    if waveform == "sine":
        return np.sin(2.0 * math.pi * phase)
    saw = 2.0 * phase - 1.0
    if waveform == "saw":
        return saw
    if waveform == "triangle":
        return 2.0 * np.abs(saw) - 1.0
    return np.where(phase < _HALF_CYCLE, 1.0, -1.0).astype(np.float64)


def additive(
    hz: float, seconds: float, amplitudes: list[float], sample_rate: int = SAMPLE_RATE
) -> Signal:
    """Sum of harmonics: amplitudes[k] scales the (k+1)th multiple of ``hz``."""
    total = np.zeros(int(seconds * sample_rate), dtype=np.float64)
    for index, amplitude in enumerate(amplitudes):
        total += amplitude * oscillator(hz * (index + 1), seconds, "sine", sample_rate)
    return total


def adsr(envelope: Envelope, seconds: float, sample_rate: int = SAMPLE_RATE) -> Signal:
    """Gain curve of an ADSR envelope over ``seconds``.

    The release is carved out of the END of the duration rather than added
    after it, so a note of N seconds is exactly N seconds long and a
    sequencer can lay notes end to end without them overlapping.
    """
    frames = max(int(seconds * sample_rate), 0)
    gain = np.zeros(frames, dtype=np.float64)
    attack = min(int(envelope.attack * sample_rate), frames)
    decay = min(int(envelope.decay * sample_rate), frames - attack)
    release = min(int(envelope.release * sample_rate), frames - attack - decay)
    sustain_start = attack + decay
    sustain_end = frames - release
    gain[:attack] = np.linspace(0.0, 1.0, attack, endpoint=False)
    gain[attack:sustain_start] = np.linspace(
        1.0, envelope.sustain, decay, endpoint=False
    )
    gain[sustain_start:sustain_end] = envelope.sustain
    gain[sustain_end:] = np.linspace(envelope.sustain, 0.0, release, endpoint=False)
    return gain


def lowpass(signal: Signal, cutoff_hz: float, sample_rate: int = SAMPLE_RATE) -> Signal:
    """One-pole low-pass: the cheapest way to make a bright sound darker."""
    if cutoff_hz <= 0.0:
        return np.zeros_like(signal)
    alpha = 1.0 - math.exp(-2.0 * math.pi * cutoff_hz / sample_rate)
    out = np.empty_like(signal)
    state = 0.0
    for index, sample in enumerate(signal):
        state += alpha * (sample - state)
        out[index] = state
    return out


def detune(hz: float, cents: float) -> float:
    """Frequency shifted by a number of cents (100 per semitone)."""
    return float(hz * 2.0 ** (cents / 1200.0))


def mix(*signals: Signal) -> Signal:
    """Sum signals of any lengths, padding the shorter ones with silence."""
    if not signals:
        return np.zeros(0, dtype=np.float64)
    length = max(len(s) for s in signals)
    total = np.zeros(length, dtype=np.float64)
    for signal in signals:
        total[: len(signal)] += signal
    return total


def normalize(signal: Signal, peak: float = DEFAULT_PEAK) -> Signal:
    """Scale so the loudest sample sits at ``peak``; silence stays silence."""
    loudest = float(np.max(np.abs(signal))) if len(signal) else 0.0
    if not loudest:
        return signal.copy()
    return signal * (peak / loudest)


def to_int16(signal: Signal) -> npt.NDArray[np.int16]:
    """Clip to [-1, 1] and scale to 16-bit PCM."""
    return (np.clip(signal, -1.0, 1.0) * _INT16_FULL_SCALE).astype(np.int16)
