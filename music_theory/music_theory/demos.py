# Copyright (c) 2026 Krzysztof Rudnicki
"""The demo registry: one entry per article section, in reading order."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from music_theory import demos_a, demos_b, synth

if TYPE_CHECKING:
    from collections.abc import Callable

    from music_theory.demo_support import Demo

REGISTRY: dict[str, Callable[[], Demo]] = {
    "tone": demos_a.tone_demo,
    "envelope": demos_a.envelope_demo,
    "waveforms": demos_a.waveforms_demo,
    "octaves": demos_a.octaves_demo,
    "consonance": demos_a.consonance_demo,
    "comma": demos_a.comma_demo,
    "temperament": demos_a.temperament_demo,
    "divisions": demos_a.divisions_demo,
    "scale": demos_b.scale_demo,
    "modes": demos_b.modes_demo,
    "chords": demos_b.chords_demo,
    "diatonic": demos_b.diatonic_demo,
    "transpose": demos_b.transpose_demo,
    "resolution": demos_b.resolution_demo,
    "progressions": demos_b.progressions_demo,
    "piece": demos_b.piece_demo,
    "bracket": demos_b.bracket_demo,
}


def run(name: str) -> Demo:
    """Build one demo by name."""
    if name not in REGISTRY:
        msg = f"unknown demo {name!r}; choose one of {tuple(REGISTRY)}"
        raise ValueError(msg)
    demo = REGISTRY[name]()
    # Every demo leaves the same headroom, so switching between files is not
    # a volume jump and no render sits exactly on full scale.
    return replace(demo, signal=synth.normalize(demo.signal))


def selected(name: str) -> list[str]:
    """Names to run for a CLI argument: one name, or "all"."""
    if name == "all":
        return list(REGISTRY)
    run_check = run  # validates the name eagerly for a clear error
    if name not in REGISTRY:
        run_check(name)
    return [name]
