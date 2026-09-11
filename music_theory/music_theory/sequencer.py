# Copyright (c) 2026 Krzysztof Rudnicki
"""Sequencer: put notes on a beat grid and render them to one buffer.

Article section 10 covers notation as a serialization format for exactly
this: a note is a pitch plus a start and a length measured in beats, and
tempo is what turns beats into seconds. Rendering to a FIXED length in
beats is what makes a loop close on a bar boundary.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from music_theory import pitch, synth

## A 4/4 bar, the article's default and the only meter used here.
BEATS_PER_BAR = 4
SECONDS_PER_MINUTE = 60.0


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
        if start >= len(total):
            continue
        note = render_note(event, tempo_bpm, sample_rate)
        end = min(start + len(note), len(total))
        total[start:end] += note[: end - start]
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
