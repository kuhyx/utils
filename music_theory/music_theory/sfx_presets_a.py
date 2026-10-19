# Copyright (c) 2026 Krzysztof Rudnicki
"""Spell presets, part one: arcane, fire and water (cast, hit, impact).

Recipes follow spellcode's research note R1 section 6 where it gives one;
arcane has none there, so its recipe is this module's own: a "plain magic"
voice of triangle and pulse waves with ring-modulated shimmer, so it stays
recognisably tonal next to the noise-heavy elements. Every cast slides UP
(charge, R1 section 5), every hit slides down or bursts, and every impact
outlasts its hit and adds a sub or rumble for weight.
"""

from __future__ import annotations

from music_theory.envelopes import Shape
from music_theory.sfx import Filter, Grit, Layer, Sfx, Tone
from music_theory.sfx_layers import crackle, make, rumble, sub, transient, whoosh
from music_theory.sweep import Pitch

CAST_PEAK = 0.6
HIT_PEAK = 0.7
IMPACT_PEAK = 0.9

ARCANE: tuple[Sfx, ...] = (
    make(
        "arcane_cast",
        Layer(
            Tone("triangle", pitch=Pitch(hz=(330.0, 990.0), vibrato_semitones=0.3)),
            Shape(attack=0.03, hold=0.15, decay=0.12),
        ),
        Layer(
            Tone("square", duty=0.25, pitch=Pitch(hz=(660.0, 1980.0))),
            Shape(attack=0.05, hold=0.12, decay=0.1),
            Filter("lowpass", (1500.0, 5000.0)),
            gain=0.3,
        ),
        peak=CAST_PEAK,
    ),
    make(
        "arcane_hit",
        transient(0.01, 3000.0, 0.6),
        Layer(
            Tone("square", duty=0.25, pitch=Pitch(hz=(1200.0, 300.0))),
            Shape(attack=0.002, hold=0.01, punch=0.3, decay=0.12),
            Filter("lowpass", (4000.0,)),
            Grit(ring_hz=220.0),
        ),
        peak=HIT_PEAK,
    ),
    make(
        "arcane_impact",
        transient(0.012, 2000.0),
        Layer(
            Tone("square", pitch=Pitch(hz=(800.0, 120.0))),
            Shape(attack=0.002, hold=0.03, punch=0.4, decay=0.3),
            Filter("lowpass", (3000.0, 600.0), resonance=3.0),
            Grit(ring_hz=90.0),
        ),
        sub(110.0, 45.0, 0.3),
        rumble(800.0, Shape(attack=0.01, hold=0.05, decay=0.4), 0.4),
        peak=IMPACT_PEAK,
    ),
)

FIRE: tuple[Sfx, ...] = (
    make(
        "fire_cast",
        whoosh((400.0, 1500.0), Shape(attack=0.12, hold=0.03, decay=0.12)),
        crackle(
            25.0,
            Shape(attack=0.05, hold=0.15, decay=0.07),
            Filter("highpass", (2000.0,)),
            0.5,
        ),
        Layer(
            Tone("saw", pitch=Pitch(hz=(110.0, 220.0))),
            Shape(attack=0.1, hold=0.05, decay=0.12),
            Filter("lowpass", (600.0,)),
            gain=0.3,
        ),
        peak=CAST_PEAK,
    ),
    make(
        "fire_hit",
        transient(0.008, 2000.0),
        rumble(2000.0, Shape(attack=0.002, hold=0.03, punch=0.5, decay=0.15), 1.0),
        crackle(
            20.0,
            Shape(attack=0.0, hold=0.05, decay=0.1),
            Filter("highpass", (1500.0,)),
            0.4,
        ),
        peak=HIT_PEAK,
    ),
    make(
        "fire_impact",
        rumble(2000.0, Shape(attack=0.002, hold=0.05, punch=0.5, decay=0.25), 1.0),
        crackle(
            20.0,
            Shape(attack=0.01, hold=0.15, decay=0.25),
            Filter("highpass", (1500.0,)),
        ),
        rumble(400.0, Shape(attack=0.01, hold=0.1, decay=0.3)),
        sub(70.0, 40.0, 0.25),
        peak=IMPACT_PEAK,
    ),
)

## Bloops: a sine flicking 300 -> 1200 Hz in 30 ms, retriggered, each one
## at a random pitch offset so a run of them sounds like water, not a beep.
_BLOOP = Tone(
    "sine",
    pitch=Pitch(
        hz=(300.0, 1200.0),
        glide=0.03,
        repeat=0.05,
        jump_semitones=4.0,
        jump_every=0.05,
    ),
)

WATER: tuple[Sfx, ...] = (
    make(
        "water_cast",
        Layer(_BLOOP, Shape(attack=0.01, hold=0.2, decay=0.1), gain=0.7),
        whoosh((800.0, 3000.0), Shape(attack=0.1, hold=0.1, decay=0.1), 1.5, 0.5),
        peak=CAST_PEAK,
    ),
    make(
        "water_hit",
        whoosh(
            (3000.0, 800.0),
            Shape(attack=0.003, hold=0.02, punch=0.3, decay=0.23),
            1.0,
        ),
        Layer(_BLOOP, Shape(attack=0.0, hold=0.1, decay=0.05), gain=0.5),
        peak=HIT_PEAK,
    ),
    make(
        "water_impact",
        transient(0.01, 1500.0),
        whoosh(
            (3000.0, 600.0),
            Shape(attack=0.003, hold=0.05, punch=0.4, decay=0.35),
            0.9,
        ),
        Layer(_BLOOP, Shape(attack=0.0, hold=0.3, decay=0.1), gain=0.5, delay=0.05),
        sub(80.0, 40.0, 0.25, 0.7),
        peak=IMPACT_PEAK,
    ),
)
