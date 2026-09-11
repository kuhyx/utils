# Copyright (c) 2026 Krzysztof Rudnicki
"""Shared plumbing for the demos: a result type and a few signal builders."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from music_theory import pitch, sequencer, synth

## Demo notes get a short envelope so consecutive tones never click.
NOTE_ENVELOPE = synth.Envelope(0.01, 0.02, 0.9, 0.05)

## Silence between tones so the ear resets.
GAP_SECONDS = 0.08

## Tempo for the note sequences: quick enough to hear as a line.
DEMO_TEMPO = 150.0


@dataclass(frozen=True)
class Demo:
    """A rendered demo: what it demonstrates, the facts, and the audio."""

    name: str
    section: str
    facts: tuple[str, ...]
    signal: synth.Signal


def tone(hz: float, seconds: float, waveform: synth.Waveform = "sine") -> synth.Signal:
    """One enveloped tone at a frequency."""
    return synth.oscillator(hz, seconds, waveform) * synth.adsr(NOTE_ENVELOPE, seconds)


def tones(
    frequencies: list[float], seconds: float, waveform: synth.Waveform = "sine"
) -> synth.Signal:
    """Tones one after another with a short gap between them."""
    gap = np.zeros(int(GAP_SECONDS * synth.SAMPLE_RATE))
    parts = [tone(hz, seconds, waveform) for hz in frequencies]
    return np.concatenate([np.concatenate((part, gap)) for part in parts])


def pair(hz_low: float, hz_high: float, seconds: float) -> synth.Signal:
    """Two tones sounded together, at equal level."""
    return synth.normalize(
        tone(hz_low, seconds) + tone(hz_high, seconds), synth.DEFAULT_PEAK
    )


def note_line(midis: list[int], beats_each: float = 0.5) -> synth.Signal:
    """A melodic line of MIDI notes, rendered through the sequencer."""
    events = sequencer.sequence(midis, beats_each, "triangle", NOTE_ENVELOPE)
    return sequencer.render(events, DEMO_TEMPO, beats_each * len(midis))


def chord_line(chords: list[list[int]], beats_each: float = 2.0) -> synth.Signal:
    """Chords one after another, each held for ``beats_each``."""
    events: list[sequencer.NoteEvent] = []
    for index, notes in enumerate(chords):
        events += sequencer.stack(
            notes, index * beats_each, beats_each, "triangle", NOTE_ENVELOPE
        )
    return sequencer.render(events, DEMO_TEMPO, beats_each * len(chords))


def names(midis: list[int]) -> str:
    """Note names of a list of MIDI numbers, space separated."""
    return " ".join(pitch.note_name(m) for m in midis)
