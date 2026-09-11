# Copyright (c) 2026 Krzysztof Rudnicki
"""Demos for article sections 1-5: sound, timbre, octaves, the comma, temperament."""

from __future__ import annotations

import numpy as np

from music_theory import analysis, pitch, synth, tuning
from music_theory.demo_support import Demo, pair, tone, tones

_A4 = pitch.A4_HZ
_A3 = 220.0
_LONG = 1.0
_SHORT = 0.5
_OCTAVES = (55.0, 110.0, 220.0, 440.0, 880.0)
_MAX_DIVISIONS = 25
_SHOWN_DIVISIONS = (5, 7, 12, 19, 24)
_STRUCK = synth.Envelope(0.01, 0.1, 0.6, 0.2)
_BOWED = synth.Envelope(0.5, 0.1, 0.8, 0.2)


def tone_demo() -> Demo:
    """Section 1: a sound is a number that changes over time."""
    signal = tone(_A4, _LONG)
    return Demo(
        "tone",
        "1 sound as numerical change",
        (
            f"A4 = {_A4:.0f} Hz = MIDI {pitch.A4_MIDI}",
            f"one semitone up multiplies by {pitch.semitone_ratio(1):.6f}",
            f"FFT peak of the render: {analysis.dominant_frequency(signal):.1f} Hz",
        ),
        signal,
    )


def envelope_demo() -> Demo:
    """Section 2: a 10 ms attack sounds struck, a 500 ms attack sounds bowed."""
    seconds = 1.2
    struck = synth.oscillator(_A3, seconds) * synth.adsr(_STRUCK, seconds)
    bowed = synth.oscillator(_A3, seconds) * synth.adsr(_BOWED, seconds)
    signal = synth.mix(struck, _shift(bowed, seconds + 0.3))
    return Demo(
        "envelope",
        "2 envelopes",
        (
            (
                f"same {_A3:.0f} Hz sine twice: "
                f"attack {_STRUCK.attack * 1000:.0f} ms then "
                f"{_BOWED.attack * 1000:.0f} ms"
            ),
            "the release fades to zero so neither note ends in a click",
        ),
        signal,
    )


def waveforms_demo() -> Demo:
    """Section 2: four overtone recipes at the same pitch."""
    parts = [tone(_A3, _SHORT, w) for w in synth.WAVEFORMS]
    facts = tuple(
        f"{w}: spectral centroid {analysis.spectral_centroid(p):.0f} Hz"
        for w, p in zip(synth.WAVEFORMS, parts, strict=True)
    )
    gap = np.zeros(int(0.2 * synth.SAMPLE_RATE))
    signal = np.concatenate([np.concatenate((part, gap)) for part in parts])
    return Demo(
        "waveforms",
        "2 timbre",
        (*facts, "same pitch, only the overtones differ"),
        signal,
    )


def octaves_demo() -> Demo:
    """Section 3: doubling the frequency gives the same note."""
    return Demo(
        "octaves",
        "3 octaves",
        tuple(
            f"{hz:.0f} Hz = {pitch.note_name(round(pitch.hz_to_midi(hz)))}"
            for hz in _OCTAVES
        ),
        tones(list(_OCTAVES), _SHORT),
    )


def consonance_demo() -> Demo:
    """Section 3: simple ratios lock in fast; the tritone never does."""
    pairs = [
        ("octave", 2.0),
        ("perfect fifth", 1.5),
        ("perfect fourth", 4.0 / 3.0),
        ("major third", 1.25),
        ("minor second", 16.0 / 15.0),
        ("tritone", tuning.TRITONE_RATIO),
    ]
    facts = []
    for name, _ in pairs:
        if name == "tritone":
            facts.append("tritone (sqrt 2): the pattern never repeats")
        else:
            facts.append(
                f"{name}: repeats after "
                f"{tuning.repeat_cycles(tuning.JUST_RATIOS[name])} cycles"
            )
    signal = synth.mix(
        *[_shift(pair(_A3, _A3 * r, 0.8), i * 1.0) for i, (_, r) in enumerate(pairs)]
    )
    return Demo("consonance", "3 consonance", tuple(facts), signal)


def comma_demo() -> Demo:
    """Section 4: twelve fifths overshoot seven octaves, audibly."""
    comma = tuning.pythagorean_comma()
    beats = tuning.beat_frequency(_A4, _A4 * comma)
    seconds = 2.0
    return Demo(
        "comma",
        "4 the Pythagorean comma",
        (
            f"(3/2)^12 / 2^7 = {comma:.6f} ({pitch.cents(comma):.2f} cents)",
            "3^n can never equal 2^m: both are prime, so no n and m close the loop",
            f"A4 against A4 x comma beats {beats:.1f} times/s",
        ),
        pair(_A4, _A4 * comma, seconds),
    )


def temperament_demo() -> Demo:
    """Section 5: twelve equal steps, and what the fifth costs."""
    steps = [
        _A3 * pitch.semitone_ratio(n) for n in range(pitch.SEMITONES_PER_OCTAVE + 1)
    ]
    fifth = tuning.fifth_error(pitch.SEMITONES_PER_OCTAVE)
    return Demo(
        "temperament",
        "5 equal temperament",
        (
            f"step = 2^(1/12) = {pitch.semitone_ratio(1):.6f}",
            (
                f"tempered fifth = 2^(7/12) = {fifth.ratio:.6f}, "
                f"{fifth.error * 100:.3f} % flat of 3/2"
            ),
            f"MIDI 69 -> {pitch.midi_to_hz(69):.1f} Hz",
        ),
        tones(steps, 0.25),
    )


def divisions_demo() -> Demo:
    """Section 5: brute-force why the octave has twelve notes."""
    first = tuning.first_acceptable_division(_MAX_DIVISIONS)
    facts = [
        f"{s.divisions:2d}-TET: fifth = step {s.step:2d} = {s.ratio:.5f}, "
        f"error {s.error * 100:.3f} %"
        for s in sorted(
            tuning.best_divisions(_MAX_DIVISIONS), key=lambda s: s.divisions
        )
        if s.divisions in _SHOWN_DIVISIONS
    ]
    facts.append(
        f"first division within {tuning.ACCEPTABLE_FIFTH_ERROR * 100:.1f} %: {first}"
    )
    frequencies = []
    for n in _SHOWN_DIVISIONS:
        frequencies += [_A3, _A3 * 1.5, _A3 * tuning.fifth_error(n).ratio]
    return Demo("divisions", "5 why twelve", tuple(facts), tones(frequencies, 0.3))


def _shift(signal: synth.Signal, seconds: float) -> synth.Signal:
    """The signal preceded by ``seconds`` of silence."""
    return np.concatenate((np.zeros(int(seconds * synth.SAMPLE_RATE)), signal))
