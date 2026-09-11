# Copyright (c) 2026 Krzysztof Rudnicki
"""Compose: the article's closing example, generalised into a recipe.

Article section 11: pick a key, pick a progression, play a bass note, an
arpeggio and a melody drawn from the scale. Constraining every voice to
the scale is what makes any melody "fit". Everything is derived from one
frozen ``Recipe`` plus a seed, so the same recipe always renders the same
bytes -- the property a game asset manifest needs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace

import numpy as np

from music_theory import degrade, pitch, progressions, scales, sequencer, synth
from music_theory.pitch import SEMITONES_PER_OCTAVE

## Voice levels, chosen so the bass carries and the melody sits on top.
BASS_VELOCITY = 0.9
ARPEGGIO_VELOCITY = 0.35
MELODY_VELOCITY = 0.5

## Eighth-note arpeggio: two chord tones per beat.
ARPEGGIO_NOTES_PER_BEAT = 2
_ARPEGGIO_ORDER = (0, 1, 2, 1)

## The melody wanders inside two octaves above the root, one step at a time.
MELODY_RANGE_DEGREES = 14
_MELODY_STEPS = (-2, -1, -1, 0, 1, 1, 2)

BASS_ENVELOPE = synth.Envelope(0.02, 0.1, 0.7, 0.2)
ARPEGGIO_ENVELOPE = synth.Envelope(0.005, 0.05, 0.5, 0.05)
MELODY_ENVELOPE = synth.Envelope(0.02, 0.08, 0.6, 0.1)


@dataclass(frozen=True)
class Recipe:
    """Everything that decides what a piece sounds like."""

    key: str = "A3"
    mode: str = "minor"
    tempo_bpm: float = 100.0
    progression: tuple[int, ...] = (1, 6, 3, 7)
    bars: int = 8
    seed: int = 0
    waveform: synth.Waveform = "saw"
    degrade: float = 0.0
    sample_rate: int = synth.SAMPLE_RATE

    def to_dict(self) -> dict[str, object]:
        """JSON-ready form (tuples become lists)."""
        data = asdict(self)
        data["progression"] = list(self.progression)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Recipe:
        """Inverse of ``to_dict``; unknown keys and wrong types are errors."""
        unknown = set(data) - {field.name for field in fields(cls)}
        if unknown:
            msg = f"unknown recipe keys: {sorted(unknown)}"
            raise ValueError(msg)
        base = cls()
        return cls(
            key=_as_str(data.get("key", base.key)),
            mode=_as_str(data.get("mode", base.mode)),
            tempo_bpm=_as_float(data.get("tempo_bpm", base.tempo_bpm)),
            progression=_as_ints(data.get("progression", base.progression)),
            bars=_as_int(data.get("bars", base.bars)),
            seed=_as_int(data.get("seed", base.seed)),
            waveform=_as_waveform(data.get("waveform", base.waveform)),
            degrade=_as_float(data.get("degrade", base.degrade)),
            sample_rate=_as_int(data.get("sample_rate", base.sample_rate)),
        )


def _as_str(value: object) -> str:
    if not isinstance(value, str):
        msg = f"expected a string, got {value!r}"
        raise TypeError(msg)
    return value


def _as_float(value: object) -> float:
    # bool is an int subclass; a recipe with tempo `true` is a typo, not 1 bpm.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        msg = f"expected a number, got {value!r}"
        raise TypeError(msg)
    return float(value)


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"expected an integer, got {value!r}"
        raise TypeError(msg)
    return value


def _as_ints(value: object) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple)):
        msg = f"expected a list of integers, got {value!r}"
        raise TypeError(msg)
    return tuple(_as_int(item) for item in value)


def _as_waveform(value: object) -> synth.Waveform:
    name = _as_str(value)
    for waveform in synth.WAVEFORMS:
        if waveform == name:
            return waveform
    msg = f"unknown waveform {name!r}; choose one of {synth.WAVEFORMS}"
    raise ValueError(msg)


def effective(recipe: Recipe) -> Recipe:
    """The recipe after its own ``degrade`` amount has darkened it."""
    return degrade.apply_to_recipe(recipe)


def _chords(recipe: Recipe) -> list[progressions.ProgressionChord]:
    root = pitch.parse_note(recipe.key)
    pattern = scales.pattern_named(recipe.mode)
    return progressions.chords_for(root, pattern, recipe.progression)


def bass_line(recipe: Recipe) -> list[sequencer.NoteEvent]:
    """One whole-bar root note per bar, an octave below the chord."""
    chords = _chords(recipe)
    beats = sequencer.BEATS_PER_BAR
    return [
        sequencer.NoteEvent(
            chords[bar_index % len(chords)].notes[0] - SEMITONES_PER_OCTAVE,
            bar_index * beats,
            beats,
            BASS_VELOCITY,
            "triangle",
            BASS_ENVELOPE,
        )
        for bar_index in range(recipe.bars)
    ]


def arpeggio(recipe: Recipe) -> list[sequencer.NoteEvent]:
    """Chord tones cycled in eighth notes, low-high-low, every bar."""
    chords = _chords(recipe)
    per_bar = sequencer.BEATS_PER_BAR * ARPEGGIO_NOTES_PER_BEAT
    length = 1.0 / ARPEGGIO_NOTES_PER_BEAT
    result = []
    for bar_index in range(recipe.bars):
        notes = chords[bar_index % len(chords)].notes
        for slot in range(per_bar):
            midi = notes[_ARPEGGIO_ORDER[slot % len(_ARPEGGIO_ORDER)] % len(notes)]
            start = bar_index * sequencer.BEATS_PER_BAR + slot * length
            result.append(
                sequencer.NoteEvent(
                    midi,
                    start,
                    length,
                    ARPEGGIO_VELOCITY,
                    recipe.waveform,
                    ARPEGGIO_ENVELOPE,
                )
            )
    return result


def melody(recipe: Recipe) -> list[sequencer.NoteEvent]:
    """A seeded random walk over scale degrees, one quarter note per beat.

    Beat one of every bar snaps to a chord tone so the line agrees with the
    harmony under it; the other beats just stay in the scale, which is
    enough for them to sound intentional.
    """
    rng = np.random.default_rng(recipe.seed)
    root = pitch.parse_note(recipe.key) + SEMITONES_PER_OCTAVE
    pattern = scales.pattern_named(recipe.mode)
    chords = _chords(recipe)
    rest_chance = degrade.rest_probability(recipe.degrade)
    degree = len(pattern)
    result = []
    for beat in range(recipe.bars * sequencer.BEATS_PER_BAR):
        bar_index, position = divmod(beat, sequencer.BEATS_PER_BAR)
        step = int(rng.choice(_MELODY_STEPS))
        degree = int(np.clip(degree + step, 0, MELODY_RANGE_DEGREES))
        midi = scales.pitch_at_degree(root, pattern, degree)
        if not position:
            midi = _nearest_chord_tone(midi, chords[bar_index % len(chords)].notes)
        if rng.random() < rest_chance:
            continue
        cents = degrade.detune_cents(recipe.degrade, rng)
        result.append(
            sequencer.NoteEvent(
                midi, beat, 1.0, MELODY_VELOCITY, "triangle", MELODY_ENVELOPE, cents
            )
        )
    return result


def _nearest_chord_tone(midi: int, chord: tuple[int, ...]) -> int:
    candidates = [
        n + o for n in chord for o in (-SEMITONES_PER_OCTAVE, 0, SEMITONES_PER_OCTAVE)
    ]
    return min(candidates, key=lambda n: (abs(n - midi), n))


def events(recipe: Recipe) -> list[sequencer.NoteEvent]:
    """Every note of the piece, from the degrade-adjusted recipe."""
    adjusted = effective(recipe)
    return bass_line(adjusted) + arpeggio(adjusted) + melody(adjusted)


def length_beats(recipe: Recipe) -> float:
    """Total length in beats: bars times four."""
    return float(recipe.bars * sequencer.BEATS_PER_BAR)


def compose(recipe: Recipe) -> synth.Signal:
    """Render the piece to a loop-length signal, degraded and normalised."""
    adjusted = effective(recipe)
    signal = sequencer.render(
        events(recipe), adjusted.tempo_bpm, length_beats(adjusted), adjusted.sample_rate
    )
    signal = degrade.process(
        signal, adjusted.degrade, adjusted.sample_rate, adjusted.seed
    )
    return synth.normalize(signal)


def with_degrade(recipe: Recipe, amount: float) -> Recipe:
    """The same recipe at another degrade amount: the compositional bracket."""
    return replace(recipe, degrade=amount)
