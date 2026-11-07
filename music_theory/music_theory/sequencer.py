# Copyright (c) 2026 Krzysztof Rudnicki
"""Sequencer: put notes on a beat grid and render them to one buffer.

Article section 10 covers notation as a serialization format for exactly
this: a note is a pitch plus a start and a length measured in beats, and
tempo is what turns beats into seconds. Rendering to a FIXED length in
beats is what makes a loop close on a bar boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np

from music_theory import biquad, pitch, synth

if TYPE_CHECKING:
    from collections.abc import Sequence

## A 4/4 bar, the article's default and what every ``Recipe`` renders in.
BEATS_PER_BAR = 4
SECONDS_PER_MINUTE = 60.0

## Beats are always quarter notes (tempo counts them), so a meter's bottom
## number only rescales: 6/8 is three quarter beats in two groups of three.
QUARTER = 4
## Halves, quarters, eighths: anything finer would split a drum eighth.
METER_DENOMINATORS = (2, 4, 8)

type DrumKind = Literal["kick", "snare", "hat"]
DRUM_KINDS: tuple[DrumKind, ...] = ("kick", "snare", "hat")
## Noise drums: (filter, cutoff Hz, decay time constant in seconds). Low
## noise thumps, mid noise cracks, high noise ticks.
_DRUMS: dict[DrumKind, tuple[biquad.FilterKind, float, float]] = {
    "kick": ("lowpass", 160.0, 0.07),
    "snare": ("bandpass", 1800.0, 0.05),
    "hat": ("highpass", 7000.0, 0.015),
}
## Short linear fade so a hit cut at its slot never ends in a click.
_FADE_SECONDS = 0.005


@dataclass(frozen=True)
class Meter:
    """Time signature: ``numerator`` notes of 1/``denominator`` per bar."""

    numerator: int = BEATS_PER_BAR
    denominator: int = QUARTER

    def __post_init__(self) -> None:
        """Reject meters the beat grid cannot hold."""
        if self.numerator <= 0 or self.denominator not in METER_DENOMINATORS:
            msg = (
                f"unsupported meter {self}; bottom must be one of {METER_DENOMINATORS}"
            )
            raise ValueError(msg)

    def __str__(self) -> str:
        """The usual written form, e.g. ``3/4``."""
        return f"{self.numerator}/{self.denominator}"

    @property
    def beats_per_bar(self) -> float:
        """Quarter-note beats in one bar: 3/4 and 6/8 are both 3."""
        return self.numerator * QUARTER / self.denominator

    @classmethod
    def parse(cls, text: str) -> Meter:
        """Meter from ``"3/4"``-style text."""
        top, _, bottom = text.partition("/")
        if not (top.isdigit() and bottom.isdigit()):
            msg = f"not a meter: {text!r}"
            raise ValueError(msg)
        return cls(int(top), int(bottom))


@dataclass(frozen=True)
class DrumHit:
    """One unpitched hit: kind, start and slot length in beats, 0..1 velocity."""

    kind: DrumKind
    start_beat: float
    length_beats: float
    velocity: float = 1.0


@dataclass(frozen=True)
class NoteEvent:
    """One note: MIDI pitch, start and length in beats, 0..1 velocity."""

    midi: int
    start_beat: float
    length_beats: float
    velocity: float = 1.0
    waveform: synth.Waveform = "sine"
    envelope: synth.Envelope = synth.DEFAULT_ENVELOPE
    ## Detune in cents, applied at render time; the pitch stays an integer
    ## so the note is still addressable by scale degree.
    cents: float = 0.0


def beat_seconds(tempo_bpm: float) -> float:
    """Length of one beat at a tempo."""
    if tempo_bpm <= 0.0:
        msg = f"tempo must be positive, got {tempo_bpm}"
        raise ValueError(msg)
    return SECONDS_PER_MINUTE / tempo_bpm


def loop_frames(
    tempo_bpm: float, beats: float, sample_rate: int = synth.SAMPLE_RATE
) -> int:
    """Frames in ``beats`` at a tempo, floored so a loop never overruns its bar."""
    return int(beats * beat_seconds(tempo_bpm) * sample_rate)


def render_note(event: NoteEvent, tempo_bpm: float, sample_rate: int) -> synth.Signal:
    """Samples of one note: oscillator times envelope times velocity."""
    seconds = event.length_beats * beat_seconds(tempo_bpm)
    hz = synth.detune(pitch.midi_to_hz(event.midi), event.cents)
    tone = synth.oscillator(hz, seconds, event.waveform, sample_rate)
    return tone * synth.adsr(event.envelope, seconds, sample_rate) * event.velocity


def render(
    events: list[NoteEvent],
    tempo_bpm: float,
    length_beats: float,
    sample_rate: int = synth.SAMPLE_RATE,
) -> synth.Signal:
    """Mix every note into a buffer exactly ``length_beats`` long.

    Notes that run past the end are cut, not wrapped: a loop that must end
    on the bar is more important than a note's tail.
    """
    total = np.zeros(
        loop_frames(tempo_bpm, length_beats, sample_rate), dtype=np.float64
    )
    for event in events:
        start = loop_frames(tempo_bpm, event.start_beat, sample_rate)
        if start < len(total):
            _add_at(total, start, render_note(event, tempo_bpm, sample_rate))
    return total


def _add_at(total: synth.Signal, start: int, sound: synth.Signal) -> None:
    end = min(start + len(sound), len(total))
    total[start:end] += sound[: end - start]


def drum_sample(
    kind: DrumKind,
    frames: int,
    rng: np.random.Generator,
    sample_rate: int = synth.SAMPLE_RATE,
) -> synth.Signal:
    """Filtered noise with an exponential decay, peak 1, faded to 0 at the end."""
    if kind not in _DRUMS:
        msg = f"unknown drum {kind!r}; choose one of {DRUM_KINDS}"
        raise ValueError(msg)
    shape, cutoff, decay = _DRUMS[kind]
    times = np.arange(frames, dtype=np.float64) / sample_rate
    hit = biquad.biquad(
        rng.uniform(-1.0, 1.0, frames), shape, cutoff, sample_rate=sample_rate
    ) * np.exp(-times / decay)
    fade = min(max(int(_FADE_SECONDS * sample_rate), 1), frames)
    hit[frames - fade :] *= np.linspace(1.0, 0.0, fade)
    return synth.normalize(hit, 1.0)


def render_hits(
    hits: list[DrumHit],
    tempo_bpm: float,
    length_beats: float,
    sample_rate: int,
    seed: Sequence[int],
) -> synth.Signal:
    """Mix drum hits into a buffer exactly ``length_beats`` long.

    Each kind's noise comes from its own generator seeded by ``seed`` plus
    the kind, so every kick is the same kick wherever it falls: a section
    sounds identical whether or not another section played before it.
    """
    total = np.zeros(loop_frames(tempo_bpm, length_beats, sample_rate))
    cache: dict[tuple[DrumKind, int], synth.Signal] = {}
    for hit in hits:
        start = loop_frames(tempo_bpm, hit.start_beat, sample_rate)
        if start >= len(total):
            continue
        frames = loop_frames(tempo_bpm, hit.length_beats, sample_rate)
        key = (hit.kind, frames)
        if key not in cache:
            rng = np.random.default_rng([*seed, DRUM_KINDS.index(hit.kind)])
            cache[key] = drum_sample(hit.kind, frames, rng, sample_rate)
        _add_at(total, start, cache[key] * hit.velocity)
    return total


def sequence(
    midis: list[int],
    beats_each: float,
    waveform: synth.Waveform = "sine",
    envelope: synth.Envelope = synth.DEFAULT_ENVELOPE,
) -> list[NoteEvent]:
    """Notes played one after another, each ``beats_each`` long."""
    return [
        NoteEvent(midi, index * beats_each, beats_each, 1.0, waveform, envelope)
        for index, midi in enumerate(midis)
    ]


def stack(
    midis: list[int],
    start_beat: float,
    beats: float,
    waveform: synth.Waveform = "sine",
    envelope: synth.Envelope = synth.DEFAULT_ENVELOPE,
) -> list[NoteEvent]:
    """Notes played together (a chord), all starting at ``start_beat``."""
    velocity = 1.0 / max(len(midis), 1)
    return [
        NoteEvent(midi, start_beat, beats, velocity, waveform, envelope)
        for midi in midis
    ]
