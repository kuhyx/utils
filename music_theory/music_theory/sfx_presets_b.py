# Copyright (c) 2026 Krzysztof Rudnicki
"""Spell presets, part two: lightning, earth and wind (cast, hit, impact).

From R1 section 6. Lightning is a full-band crack, a square wave jumping
to a random pitch every 12-15 ms and a bit-crushed 110 Hz saw buzz, with
a low thunder tail on impact. Earth is a falling sub, low-passed noise and
a rattle of gravel grains. Wind is a resonant band-pass whose centre
sweeps up then down -- flow, not impact, so it gets no transient.
"""

from __future__ import annotations

from music_theory.envelopes import Shape
from music_theory.sfx import Filter, Grit, Layer, Sfx, Tone
from music_theory.sfx_layers import crackle, make, rumble, sub, whoosh
from music_theory.sfx_presets_a import CAST_PEAK, HIT_PEAK, IMPACT_PEAK
from music_theory.sweep import Pitch

## The crack: 8 ms of unfiltered white noise.
_CRACK = Layer(Tone("noise"), Shape(attack=0.0, hold=0.002, decay=0.008))

_BUZZ = Tone("saw", pitch=Pitch(hz=(110.0,)))


def _arc(start_hz: float, end_hz: float, shape: Shape) -> Layer:
    """A square wave jumping +-7 semitones every 12 ms along a glide."""
    pitch = Pitch(hz=(start_hz, end_hz), jump_semitones=7.0, jump_every=0.012)
    return Layer(
        Tone("square", pitch=pitch), shape, Filter("highpass", (500.0,)), gain=0.6
    )


def _gravel(rate_hz: float, shape: Shape) -> Layer:
    """Stone on stone: 2 ms grains, band-passed low enough to stay heavy."""
    return crackle(rate_hz, shape, Filter("bandpass", (1500.0,), 1.5), 0.35)


LIGHTNING: tuple[Sfx, ...] = (
    make(
        "lightning_cast",
        _arc(200.0, 900.0, Shape(attack=0.05, hold=0.15, decay=0.1)),
        Layer(
            Tone("saw", pitch=Pitch(hz=(110.0, 165.0))),
            Shape(attack=0.05, hold=0.15, decay=0.1),
            grit=Grit(crush_bits=5.0),
            gain=0.4,
        ),
        crackle(
            60.0,
            Shape(attack=0.1, hold=0.1, decay=0.1),
            Filter("highpass", (4000.0,)),
            0.4,
        ),
        peak=CAST_PEAK,
    ),
    make(
        "lightning_hit",
        _CRACK,
        _arc(1200.0, 600.0, Shape(attack=0.001, hold=0.04, punch=0.3, decay=0.08)),
        Layer(
            _BUZZ,
            Shape(attack=0.002, hold=0.05, decay=0.06),
            grit=Grit(crush_bits=4.0),
            gain=0.5,
        ),
        peak=HIT_PEAK,
    ),
    make(
        "lightning_impact",
        _CRACK,
        _arc(1500.0, 500.0, Shape(attack=0.001, hold=0.06, punch=0.4, decay=0.12)),
        Layer(
            _BUZZ,
            Shape(attack=0.002, hold=0.08, decay=0.1),
            grit=Grit(crush_bits=4.0),
            gain=0.5,
        ),
        rumble(200.0, Shape(attack=0.02, hold=0.1, decay=0.7), 0.8),
        peak=IMPACT_PEAK,
    ),
)

EARTH: tuple[Sfx, ...] = (
    make(
        "earth_cast",
        Layer(
            Tone("triangle", pitch=Pitch(hz=(55.0, 140.0))),
            Shape(attack=0.08, hold=0.15, decay=0.1),
            gain=0.9,
        ),
        _gravel(60.0, Shape(attack=0.1, hold=0.15, decay=0.08)),
        rumble(300.0, Shape(attack=0.1, hold=0.1, decay=0.1), 0.3),
        peak=CAST_PEAK,
    ),
    make(
        "earth_hit",
        sub(60.0, 35.0, 0.2, 1.0),
        rumble(300.0, Shape(attack=0.002, hold=0.03, punch=0.3, decay=0.17)),
        _gravel(100.0, Shape(attack=0.0, hold=0.2, decay=0.1)),
        peak=HIT_PEAK,
    ),
    make(
        "earth_impact",
        # A thump, not a click: the contact transient low-passed, not high.
        rumble(1500.0, Shape(attack=0.0, hold=0.002, decay=0.012), 0.6),
        sub(60.0, 30.0, 0.35, 1.0),
        rumble(300.0, Shape(attack=0.002, hold=0.05, punch=0.5, decay=0.35)),
        _gravel(110.0, Shape(attack=0.02, hold=0.25, decay=0.1)),
        peak=IMPACT_PEAK,
    ),
)

WIND: tuple[Sfx, ...] = (
    make(
        "wind_cast",
        whoosh((250.0, 1800.0), Shape(attack=0.15, hold=0.1, decay=0.1), 5.0),
        whoosh((500.0, 2500.0), Shape(attack=0.1, hold=0.1, decay=0.15), 2.0, 0.4),
        peak=CAST_PEAK,
    ),
    make(
        "wind_hit",
        whoosh((300.0, 1500.0, 400.0), Shape(attack=0.08, hold=0.1, decay=0.12), 4.0),
        whoosh(
            (200.0, 900.0, 300.0), Shape(attack=0.08, hold=0.1, decay=0.12), 1.5, 0.4
        ),
        peak=HIT_PEAK,
    ),
    make(
        "wind_impact",
        whoosh((200.0, 1200.0, 300.0), Shape(attack=0.1, hold=0.3, decay=0.25), 3.0),
        rumble(250.0, Shape(attack=0.05, hold=0.2, decay=0.3), 0.6),
        Layer(
            Tone("noise"),
            Shape(attack=0.05, hold=0.1, decay=0.15),
            Filter("bandpass", (600.0, 3000.0, 800.0), resonance=6.0),
            gain=0.3,
            delay=0.1,
        ),
        peak=IMPACT_PEAK,
    ),
)
