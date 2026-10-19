# Copyright (c) 2026 Krzysztof Rudnicki
"""Envelopes for sound effects: struck, punched, and dying exponentially.

``synth.adsr`` is a sustained note's envelope -- linear segments around a
held level. A hit or a zap is never held: it rises, may kick harder for a
moment (sfxr's "punch"), and then dies away the way a real resonance does,
by a constant ratio per unit of time. That last part is what reads as
"natural"; a linear fade sounds like a volume knob being turned down.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from music_theory import synth
from music_theory.synth import SAMPLE_RATE, Signal


@dataclass(frozen=True)
class Shape:
    """Attack, hold and decay in seconds; punch boosts the start of the hold.

    ``curve`` is how many time constants the decay spans: 5 ends ~43 dB
    down, 10 sounds clipped short. The decay also fades linearly to zero
    across its length so the very last sample is silent -- no click.
    """

    attack: float = 0.005
    hold: float = 0.05
    punch: float = 0.0
    decay: float = 0.2
    curve: float = 5.0

    @property
    def seconds(self) -> float:
        """Total length of the envelope."""
        return self.attack + self.hold + self.decay


def exponential(
    frames: int, time_constant: float, sample_rate: int = SAMPLE_RATE
) -> Signal:
    """exp(-t / tau): falls by the same ratio every ``time_constant`` seconds."""
    if time_constant <= 0.0:
        msg = f"time constant must be positive, got {time_constant}"
        raise ValueError(msg)
    times = np.arange(max(frames, 0), dtype=np.float64) / sample_rate
    return np.exp(-times / time_constant)


def shape(envelope: Shape, sample_rate: int = SAMPLE_RATE) -> Signal:
    """Gain curve of a ``Shape``: ADSR's attack, then punch, then exp decay."""
    head_seconds = envelope.attack + envelope.hold
    # The attack-and-hold head IS an ADSR with full sustain and no release,
    # so it reuses that rather than growing a second linear-ramp routine.
    head = synth.adsr(
        synth.Envelope(envelope.attack, 0.0, 1.0, 0.0), head_seconds, sample_rate
    )
    attack = min(int(envelope.attack * sample_rate), len(head))
    hold = len(head) - attack
    head[attack:] *= 1.0 + envelope.punch * (1.0 - np.arange(hold) / max(hold, 1))
    frames = int(envelope.decay * sample_rate)
    position = np.arange(frames, dtype=np.float64) / max(frames, 1)
    tail = np.exp(-envelope.curve * position) * (1.0 - position)
    return np.concatenate((head, tail))
