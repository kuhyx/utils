# Copyright (c) 2026 Krzysztof Rudnicki
"""SFX presets: every sound spellcode needs, by name.

Six elements (spellcode's v1 set: arcane, fire, water, lightning, earth,
wind) times three beats (cast, hit, impact), plus the moves: dodge, a
normal and a perfect parry, and the fizzle of a spell that failed.

The moves follow sfxr's rule of thumb -- a down-slide is failure or
impact, an up-slide is reward: the perfect parry rings higher and longer
than the normal one and climbs a fifth, the fizzle slides down into a
crushed sputter.
"""

from __future__ import annotations

from dataclasses import replace

from music_theory.envelopes import Shape
from music_theory.sfx import Filter, Grit, Layer, Sfx, Tone
from music_theory.sfx_layers import chime, crackle, make, transient, whoosh
from music_theory.sfx_presets_a import ARCANE, FIRE, WATER
from music_theory.sfx_presets_b import EARTH, LIGHTNING, WIND
from music_theory.sweep import Pitch

ELEMENTS: tuple[str, ...] = ("arcane", "fire", "water", "lightning", "earth", "wind")

MOVE_PEAK = 0.6

## Inharmonic partials of a struck bar, the "chime" in R1's ice recipe.
_BAR_PARTIALS = (1.0, 2.76, 5.40)

_PERFECT_HZ = 1600.0

MOVES: tuple[Sfx, ...] = (
    make(
        "dodge",
        replace(
            whoosh((500.0, 2500.0, 700.0), Shape(attack=0.04, hold=0.04, decay=0.1)),
            tone=Tone("pink"),
        ),
        peak=MOVE_PEAK,
    ),
    make(
        "parry_normal",
        transient(0.01, 3000.0, 0.7),
        Layer(
            Tone("triangle", pitch=Pitch(hz=(900.0,))),
            Shape(attack=0.001, hold=0.01, punch=0.5, decay=0.22, curve=6.0),
            grit=Grit(ring_hz=370.0),
        ),
        Layer(
            Tone("square", duty=0.3, pitch=Pitch(hz=(1400.0,))),
            Shape(attack=0.001, hold=0.0, decay=0.12),
            grit=Grit(ring_hz=530.0),
            gain=0.3,
        ),
        peak=MOVE_PEAK,
    ),
    make(
        "parry_perfect",
        transient(0.01, 4000.0, 0.6),
        *(
            chime(_PERFECT_HZ * ratio, 0.5, 0.6 / (index + 1))
            for index, ratio in enumerate(_BAR_PARTIALS)
        ),
        chime(_PERFECT_HZ * 1.5, 0.45, 0.4, delay=0.06),
        Layer(
            Tone("square", duty=0.25, pitch=Pitch(hz=(2000.0, 4000.0))),
            Shape(attack=0.01, hold=0.04, decay=0.08),
            Filter("lowpass", (6000.0,)),
            gain=0.15,
        ),
        peak=0.8,
    ),
    make(
        "fizzle",
        Layer(
            Tone("saw", pitch=Pitch(hz=(500.0, 90.0))),
            Shape(attack=0.01, hold=0.1, decay=0.25),
            Filter("lowpass", (2500.0, 400.0)),
            Grit(crush_bits=4.0),
        ),
        crackle(
            30.0,
            Shape(attack=0.0, hold=0.15, decay=0.15),
            Filter("highpass", (1000.0,)),
            0.4,
        ),
        peak=MOVE_PEAK,
    ),
)

PRESETS: dict[str, Sfx] = {
    sound.name: sound
    for group in (ARCANE, FIRE, WATER, LIGHTNING, EARTH, WIND, MOVES)
    for sound in group
}

NAMES: tuple[str, ...] = tuple(PRESETS)


def preset(name: str) -> Sfx:
    """The preset called ``name``."""
    if name not in PRESETS:
        msg = f"unknown preset {name!r}; choose one of {NAMES}"
        raise KeyError(msg)
    return PRESETS[name]
