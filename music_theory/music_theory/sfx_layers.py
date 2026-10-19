# Copyright (c) 2026 Krzysztof Rudnicki
"""SFX layers: the recurring building blocks of a spell sound, named.

A hit is a TRANSIENT (5-20 ms of noise that sells the contact), a BODY
(the element's identity), a TAIL (filtered noise dying away) and, for
heavy hits, a SUB (a low sine falling in pitch). These helpers build the
recurring layers so a preset reads as its recipe rather than as twenty
constructor arguments.
"""

from __future__ import annotations

import zlib

from music_theory import synth
from music_theory.envelopes import Shape
from music_theory.sfx import Filter, Grit, Layer, Sfx, Tone
from music_theory.sweep import Pitch


def make(name: str, *layers: Layer, peak: float = synth.DEFAULT_PEAK) -> Sfx:
    """A named sound seeded from its name (crc32 is stable across runs)."""
    return Sfx(name, layers, seed=zlib.crc32(name.encode()), peak=peak)


def transient(
    seconds: float = 0.01, high_hz: float = 2500.0, gain: float = 0.8
) -> Layer:
    """A click of high-passed white noise: the moment of contact."""
    return Layer(
        Tone("noise"),
        Shape(attack=0.0, hold=0.002, decay=seconds, curve=6.0),
        Filter("highpass", (high_hz,)),
        gain=gain,
    )


def sub(start_hz: float, end_hz: float, seconds: float, gain: float = 0.9) -> Layer:
    """A sine dropping in pitch: weight you feel more than hear."""
    return Layer(
        Tone("sine", pitch=Pitch(hz=(start_hz, end_hz))),
        Shape(attack=0.003, hold=0.0, decay=seconds, curve=3.0),
        gain=gain,
    )


def whoosh(
    hz: tuple[float, ...], shape: Shape, q: float = 2.0, gain: float = 1.0
) -> Layer:
    """Noise through a band-pass whose centre glides through ``hz``."""
    return Layer(Tone("noise"), shape, Filter("bandpass", hz, q), gain=gain)


def rumble(cutoff_hz: float, shape: Shape, gain: float = 0.7) -> Layer:
    """Low-passed white noise: a tail, thunder, the thud under a hit.

    White rather than pink: pink's 1/f puts most of its energy below
    20 Hz, which no speaker plays and every limiter still counts.
    """
    return Layer(Tone("noise"), shape, Filter("lowpass", (cutoff_hz,)), gain=gain)


def crackle(
    rate_hz: float, shape: Shape, filtering: Filter, gain: float = 0.6
) -> Layer:
    """Sparse 2 ms noise grains at ``rate_hz``: fire crackle, gravel rattle."""
    return Layer(Tone("noise"), shape, filtering, Grit(grain_rate=rate_hz), gain=gain)


def chime(hz: float, seconds: float, gain: float = 0.6, delay: float = 0.0) -> Layer:
    """A struck sine with an exponential ring-out."""
    return Layer(
        Tone("sine", pitch=Pitch(hz=(hz,))),
        Shape(attack=0.002, hold=0.0, decay=seconds, curve=4.0),
        gain=gain,
        delay=delay,
    )
