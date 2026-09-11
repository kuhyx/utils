# Copyright (c) 2026 Krzysztof Rudnicki
"""Manifest: the recipe of every rendered file, so it can be rebuilt.

A committed audio file whose recipe lives only in a chat transcript is
unreproducible. An entry here holds the full recipe, the package version
that rendered it and the SHA-256 of the output, so a re-render can prove
it reproduced the shipped bytes -- or show exactly what changed.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from music_theory import __version__, wav

if TYPE_CHECKING:
    from pathlib import Path

    from music_theory.compose import Recipe
    from music_theory.synth import Signal

Entry = dict[str, object]


def entry(recipe: Recipe, path: Path, signal: Signal) -> Entry:
    """Provenance record for one rendered file."""
    return {
        "file": path.name,
        "recipe": recipe.to_dict(),
        "music_theory_version": __version__,
        "sample_rate": recipe.sample_rate,
        "frames": len(signal),
        "seconds": wav.duration_seconds(signal, recipe.sample_rate),
        "sha256": wav.sha256(path),
    }


def write(path: Path, entries: dict[str, Entry]) -> Path:
    """Write entries as sorted, indented JSON with a trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2, sort_keys=True) + "\n")
    return path


def read(path: Path) -> dict[str, Entry]:
    """Load a manifest written by ``write``."""
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        msg = f"{path} does not hold a manifest object"
        raise TypeError(msg)
    return data
