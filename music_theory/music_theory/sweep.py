# Copyright (c) 2026 Krzysztof Rudnicki
"""Sweep: pitch that moves, drawn by an oscillator that accumulates phase.

Not in the article, where every note holds one pitch. A sound effect's
identity is mostly its pitch MOTION: a down-slide reads as an attack or an
impact, an up-slide as a charge or a reward. ``synth.oscillator`` computes
phase as ``t * hz``, which only works for a constant ``hz`` -- feed it a
changing one and the waveform jumps. Here phase is the running sum of
``hz / sample_rate``, so any frequency curve stays continuous.

The curve is sfxr's pitch section as data: breakpoints with an exponential
glide between them, vibrato, a one-step arpeggio, random pitch jumps, and a
retrigger that restarts the slide and arpeggio every ``repeat`` seconds.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from music_theory.synth import SAMPLE_RATE, Signal, Waveform, waveshape

_SEMITONES_PER_OCTAVE = 12.0


@dataclass(frozen=True)
class Pitch:
    """A frequency curve. Times in seconds; 0 switches a feature off.

    ``hz`` are breakpoints spread evenly over ``glide`` seconds (the whole
    sound when 0) with an exponential glide between them, so one octave up
    takes the same time anywhere in the range.
    """

    hz: tuple[float, ...] = (440.0,)
    glide: float = 0.0
    vibrato_semitones: float = 0.0
    vibrato_hz: float = 6.0
    arp_ratio: float = 1.0
    arp_at: float = 0.0
    jump_semitones: float = 0.0
    jump_every: float = 0.015
    repeat: float = 0.0


def semitones(ratio_semitones: Signal | float) -> Signal:
    """Frequency ratio of a number of semitones (12 per octave)."""
    return np.asarray(
        2.0 ** (np.asarray(ratio_semitones) / _SEMITONES_PER_OCTAVE), dtype=np.float64
    )


def glide(points: tuple[float, ...], times: Signal, span: float) -> Signal:
    """Exponential interpolation through ``points`` over ``span`` seconds.

    Interpolates in log-frequency so pitch moves at an even musical rate;
    holds the last point after ``span`` (and everywhere, if ``span`` is 0).
    """
    if not points or min(points) <= 0.0:
        msg = f"glide needs positive frequencies, got {points!r}"
        raise ValueError(msg)
    logs = np.log(np.asarray(points, dtype=np.float64))
    if len(points) == 1 or span <= 0.0:
        return np.full(len(times), float(points[-1]))
    anchors = np.linspace(0.0, span, len(points))
    return np.asarray(np.exp(np.interp(times, anchors, logs)), dtype=np.float64)


def _jumps(pitch: Pitch, times: Signal, rng: np.random.Generator) -> Signal:
    """Hold a random pitch offset for ``jump_every`` seconds, then jump."""
    steps = (times / pitch.jump_every).astype(np.int64)
    offsets = rng.uniform(
        -pitch.jump_semitones, pitch.jump_semitones, int(steps[-1]) + 1
    )
    return semitones(offsets[steps])


def frequency_curve(
    pitch: Pitch, frames: int, rng: np.random.Generator, sample_rate: int = SAMPLE_RATE
) -> Signal:
    """Hz at every sample of a sound ``frames`` long."""
    times = np.arange(max(frames, 0), dtype=np.float64) / sample_rate
    if not times.size:
        return times
    local = times % pitch.repeat if pitch.repeat > 0.0 else times
    span = pitch.glide if pitch.glide > 0.0 else times[-1]
    curve = glide(pitch.hz, local, span)
    if pitch.arp_at > 0.0:
        curve = np.where(local >= pitch.arp_at, curve * pitch.arp_ratio, curve)
    if pitch.vibrato_semitones:
        wobble = np.sin(2.0 * math.pi * pitch.vibrato_hz * times)
        curve = curve * semitones(pitch.vibrato_semitones * wobble)
    if pitch.jump_semitones:
        curve = curve * _jumps(pitch, times, rng)
    return curve


def phase_oscillator(
    hz: Signal, waveform: Waveform, sample_rate: int = SAMPLE_RATE, duty: float = 0.5
) -> Signal:
    """A waveform following a per-sample frequency curve, starting at phase 0."""
    if not hz.size:
        return np.zeros(0, dtype=np.float64)
    phase = np.concatenate(([0.0], np.cumsum(hz[:-1] / sample_rate))) % 1.0
    return waveshape(phase, waveform, duty)


def ring_modulate(signal: Signal, hz: float, sample_rate: int = SAMPLE_RATE) -> Signal:
    """Multiply by a sine: each partial f becomes f - hz and f + hz.

    The result is inharmonic, which is why it reads as metal, bells and
    "magic" rather than as a note.
    """
    if not hz:
        return signal.copy()
    times = np.arange(len(signal), dtype=np.float64) / sample_rate
    return signal * np.sin(2.0 * math.pi * hz * times)
