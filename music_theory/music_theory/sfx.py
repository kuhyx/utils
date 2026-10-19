# Copyright (c) 2026 Krzysztof Rudnicki
"""SFX: an sfxr-style parameter set, rendered by this package's primitives.

Not in the article. sfxr describes a sound effect as ~20 numbers: a wave,
a pitch slide with vibrato/arpeggio/retrigger, an attack-sustain-punch-
decay envelope, filters and a little distortion. That set is here as
frozen dataclasses (grouped, so each group stays readable), and a sound is
a few LAYERS of it mixed together -- a transient that sells the hit, a
body that carries the element, a tail, sometimes a sub -- because one sfxr
voice cannot be a crackle and a rumble at once.

Rendering is deterministic: layer ``i`` of a sound draws its noise from
``default_rng([seed, i])``, so the same ``Sfx`` is the same bytes forever
and a manifest's SHA-256 can prove it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from typing import Literal

import numpy as np

from music_theory import biquad, degrade, envelopes, noise, sweep, synth

type Wave = Literal["sine", "triangle", "square", "saw", "noise", "pink"]
type FilterChoice = Literal["none", "lowpass", "highpass", "bandpass"]

WAVES: tuple[Wave, ...] = ("sine", "triangle", "square", "saw", "noise", "pink")

## CD rate: lightning cracks and high-passed hiss live above the 11 kHz a
## 22050 Hz file can hold. Pass 22050 to match the music beds instead.
SFX_SAMPLE_RATE = 44100


@dataclass(frozen=True)
class Tone:
    """The raw source: a wave, its square duty, and its pitch curve.

    The pitch is ignored by ``noise`` and ``pink``, which have none.
    """

    wave: Wave = "square"
    duty: float = 0.5
    pitch: sweep.Pitch = field(default_factory=sweep.Pitch)


@dataclass(frozen=True)
class Filter:
    """A biquad whose cutoff glides through ``hz`` over the whole layer."""

    kind: FilterChoice = "none"
    hz: tuple[float, ...] = (1000.0,)
    resonance: float = biquad.FLAT_Q


@dataclass(frozen=True)
class Grit:
    """Ring modulation, bit-crushing and grain gating; 0 switches each off."""

    ring_hz: float = 0.0
    crush_bits: float = 0.0
    grain_rate: float = 0.0
    grain_seconds: float = 0.002


@dataclass(frozen=True)
class Layer:
    """One sfxr voice placed ``delay`` seconds into the sound at ``gain``."""

    tone: Tone
    shape: envelopes.Shape
    filtering: Filter = field(default_factory=Filter)
    grit: Grit = field(default_factory=Grit)
    gain: float = 1.0
    delay: float = 0.0


@dataclass(frozen=True)
class Sfx:
    """A named sound: layers mixed, then normalised to ``peak``."""

    name: str
    layers: tuple[Layer, ...]
    seed: int = 0
    sample_rate: int = SFX_SAMPLE_RATE
    peak: float = synth.DEFAULT_PEAK

    def to_dict(self) -> dict[str, object]:
        """Every parameter as plain JSON data, for the manifest.

        Round-tripped through JSON so tuples come back as the lists a
        manifest read from disk holds, and the two compare equal.
        """
        data: dict[str, object] = json.loads(json.dumps(asdict(self)))
        return data


def _source(
    tone: Tone, frames: int, rng: np.random.Generator, sample_rate: int
) -> synth.Signal:
    if tone.wave == "noise":
        return noise.white(frames, rng)
    if tone.wave == "pink":
        return noise.pink(frames, rng)
    if tone.wave not in WAVES:
        msg = f"unknown wave {tone.wave!r}; choose one of {WAVES}"
        raise ValueError(msg)
    hz = sweep.frequency_curve(tone.pitch, frames, rng, sample_rate)
    signal = sweep.phase_oscillator(hz, tone.wave, sample_rate, tone.duty)
    if tone.wave == "square":
        # A pulse narrower than half a cycle sits off-centre (mean 2*duty-1).
        # That DC is inaudible but eats headroom and clicks at the ends.
        signal = signal - (2.0 * tone.duty - 1.0)
    return signal


def _filtered(signal: synth.Signal, spec: Filter, sample_rate: int) -> synth.Signal:
    if spec.kind == "none":
        return signal
    times = np.arange(len(signal), dtype=np.float64) / sample_rate
    span = len(signal) / sample_rate
    cutoff = sweep.glide(spec.hz, times, span)
    return biquad.biquad(signal, spec.kind, cutoff, spec.resonance, sample_rate)


def render_layer(
    layer: Layer, rng: np.random.Generator, sample_rate: int = SFX_SAMPLE_RATE
) -> synth.Signal:
    """One layer, from its own start (the delay is applied by ``render``)."""
    gain = envelopes.shape(layer.shape, sample_rate)
    frames = len(gain)
    signal = _source(layer.tone, frames, rng, sample_rate)
    grit = layer.grit
    if grit.grain_rate:
        signal = signal * noise.grains(
            frames, grit.grain_rate, grit.grain_seconds, rng, sample_rate
        )
    signal = sweep.ring_modulate(signal, grit.ring_hz, sample_rate)
    signal = _filtered(signal, layer.filtering, sample_rate)
    if grit.crush_bits:
        signal = degrade.bitcrush(signal, grit.crush_bits)
    return layer.gain * signal * gain


def render(sound: Sfx) -> synth.Signal:
    """Mix every layer at its delay and normalise the result to ``peak``."""
    voices = []
    for index, layer in enumerate(sound.layers):
        rng = np.random.default_rng([sound.seed, index])
        lead = np.zeros(int(layer.delay * sound.sample_rate), dtype=np.float64)
        body = render_layer(layer, rng, sound.sample_rate)
        voices.append(np.concatenate((lead, body)))
    return synth.normalize(synth.mix(*voices), sound.peak)
