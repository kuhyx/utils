# Copyright (c) 2026 Krzysztof Rudnicki
"""Tuning: why the tuning everyone wants cannot exist, and what we use instead.

Article sections 3, 4 and 5. Consonance is the ear finding a repeating
pattern quickly, which small-integer ratios give it. Stacking twelve pure
fifths overshoots seven octaves (the Pythagorean comma) because 3**n can
never equal 2**m, so equal temperament splits the octave into twelve equal
multiplicative steps and accepts a fifth that is 0.11 % flat everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math

## The just intervals, as the small-integer ratios the harmonic series gives.
JUST_RATIOS: dict[str, Fraction] = {
    "unison": Fraction(1, 1),
    "octave": Fraction(2, 1),
    "perfect fifth": Fraction(3, 2),
    "perfect fourth": Fraction(4, 3),
    "major third": Fraction(5, 4),
    "minor third": Fraction(6, 5),
    "major sixth": Fraction(5, 3),
    "minor second": Fraction(16, 15),
}

## The tritone: sqrt(2), halfway up the octave, no integer ratio at all.
TRITONE_RATIO = math.sqrt(2.0)

## A fifth is "acceptable" when it is within this of 3/2 (the article's bar:
## twelve is the first division whose fifth lands within about 0.1 %).
ACCEPTABLE_FIFTH_ERROR = 0.002

## How many pure fifths it takes to come back round to the same pitch class.
FIFTHS_IN_CYCLE = 12
OCTAVES_IN_CYCLE = 7

_PURE_FIFTH = 1.5
_OCTAVE = 2.0


@dataclass(frozen=True)
class DivisionScore:
    """How well an n-way equal division of the octave approximates a fifth."""

    divisions: int
    step: int
    ratio: float
    error: float


def harmonic_series(fundamental_hz: float, count: int) -> list[float]:
    """The first ``count`` harmonics: 1x, 2x, 3x ... the fundamental."""
    return [fundamental_hz * n for n in range(1, count + 1)]


def repeat_cycles(ratio: Fraction) -> int:
    """Cycles of the LOWER note before two notes' combined wave repeats.

    For 3/2 the lower note completes 2 cycles while the upper completes 3
    and the pattern restarts: the ear locks on almost at once. For 16/15 it
    takes 15 cycles, which is why a minor second sounds rough.
    """
    return ratio.denominator


def pythagorean_comma() -> float:
    """(3/2) ** 12 / 2 ** 7 -- about 1.0136, the gap that breaks pure tuning."""
    return _PURE_FIFTH**FIFTHS_IN_CYCLE / _OCTAVE**OCTAVES_IN_CYCLE


def stack_fifths(count: int) -> float:
    """Ratio after ``count`` pure fifths, folded back into one octave."""
    ratio = _PURE_FIFTH**count
    while ratio >= _OCTAVE:
        ratio /= _OCTAVE
    return ratio


def fifth_error(divisions: int) -> DivisionScore:
    """Closest step of an n-way equal division to a pure fifth, and its error."""
    if divisions <= 0:
        msg = f"divisions must be positive, got {divisions}"
        raise ValueError(msg)
    step = round(divisions * math.log2(_PURE_FIFTH))
    ratio = _OCTAVE ** (step / divisions)
    return DivisionScore(divisions, step, ratio, abs(ratio / _PURE_FIFTH - 1.0))


def best_divisions(max_divisions: int) -> list[DivisionScore]:
    """Every division up to ``max_divisions``, best fifth first.

    Brute force, exactly as the article does it: the answer to "why twelve"
    is that twelve is the smallest count whose fifth clears the bar, and the
    next improvements (19, 31, 53) buy little for a lot more notes.
    """
    scores = [fifth_error(n) for n in range(1, max_divisions + 1)]
    return sorted(scores, key=lambda score: (score.error, score.divisions))


def first_acceptable_division(
    max_divisions: int, tolerance: float = ACCEPTABLE_FIFTH_ERROR
) -> int | None:
    """Smallest division whose fifth is within ``tolerance`` of 3/2."""
    for n in range(1, max_divisions + 1):
        if fifth_error(n).error <= tolerance:
            return n
    return None


def beat_frequency(hz_a: float, hz_b: float) -> float:
    """How many times per second two close tones beat against each other."""
    return abs(hz_a - hz_b)
