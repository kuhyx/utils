# Copyright (c) 2026 Krzysztof Rudnicki
"""Score events: lay a parsed score's sections end to end on the beat grid.

``play A B A`` is a timeline: each section starts where the previous one
ended, and every bar inside it starts at a whole multiple of the meter's
beats. Pitched voices become ``NoteEvent``s, noise voices ``DrumHit``s.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from music_theory import sequencer, synth

if TYPE_CHECKING:
    from collections.abc import Iterator

    from music_theory.score import Score, Section, Voice
    from music_theory.score_tokens import Step

## Note shape for every pitched voice: struck, short decay, clean release.
NOTE_ENVELOPE = synth.Envelope(0.01, 0.08, 0.6, 0.08)


def _timeline(piece: Score) -> Iterator[tuple[float, Section]]:
    by_name = {section.name: section for section in piece.sections}
    offset = 0.0
    for name in piece.order:
        yield offset, by_name[name]
        offset += by_name[name].bars * piece.meter.beats_per_bar


def _steps(piece: Score, voice: Voice) -> Iterator[tuple[float, Step]]:
    for offset, section in _timeline(piece):
        for index, measure in enumerate(section.parts.get(voice.name, ())):
            beat = offset + index * piece.meter.beats_per_bar
            for step in measure:
                yield beat, step
                beat += step[1]


def length_beats(piece: Score) -> float:
    """Total length in quarter beats: every played bar times the meter."""
    return sum(section.bars for _, section in _timeline(piece)) * (
        piece.meter.beats_per_bar
    )


def note_events(piece: Score) -> list[sequencer.NoteEvent]:
    """Every pitched note, in play order; rests leave a gap."""
    return [
        sequencer.NoteEvent(
            value, beat, length, voice.velocity, voice.waveform, NOTE_ENVELOPE
        )
        for voice in piece.voices
        if not voice.noise
        for beat, (value, length) in _steps(piece, voice)
        if isinstance(value, int)
    ]


def drum_parts(piece: Score) -> list[tuple[int, list[sequencer.DrumHit]]]:
    """Each noise voice's hits, keyed by the voice's index (its seed salt)."""
    return [
        (
            index,
            [
                sequencer.DrumHit(value, beat, length, voice.velocity)
                for beat, (value, length) in _steps(piece, voice)
                if isinstance(value, str)
            ],
        )
        for index, voice in enumerate(piece.voices)
        if voice.noise
    ]


def render(piece: Score) -> synth.Signal:
    """Mix every voice into one buffer exactly the score's length, unnormalised."""
    beats = length_beats(piece)
    total = sequencer.render(
        note_events(piece), piece.tempo_bpm, beats, piece.sample_rate
    )
    for index, hits in drum_parts(piece):
        total += sequencer.render_hits(
            hits, piece.tempo_bpm, beats, piece.sample_rate, (piece.seed, index)
        )
    return total
