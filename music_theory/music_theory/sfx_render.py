# Copyright (c) 2026 Krzysztof Rudnicki
"""Render SFX presets to a directory of 16-bit mono WAVs plus a manifest.

One ``<name>.wav`` per preset and a ``MANIFEST.json`` holding each file's
full parameter set, seed, package version and SHA-256 -- so a game can
commit the WAVs and anyone can prove a re-render reproduced them.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from music_theory import manifest, sfx, sfx_presets, wav

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

MANIFEST_NAME = "MANIFEST.json"


def render_all(
    out_dir: Path,
    sample_rate: int = sfx.SFX_SAMPLE_RATE,
    names: Sequence[str] | None = None,
) -> dict[str, manifest.Entry]:
    """Render ``names`` (default: every preset) and merge them into the manifest."""
    manifest_path = out_dir / MANIFEST_NAME
    entries = manifest.read(manifest_path) if manifest_path.exists() else {}
    for name in sfx_presets.NAMES if names is None else names:
        sound = replace(sfx_presets.preset(name), sample_rate=sample_rate)
        signal = sfx.render(sound)
        path = wav.write(out_dir / f"{name}.wav", signal, sample_rate)
        entries[path.name] = manifest.entry(sound, path, signal)
    manifest.write(manifest_path, entries)
    return entries
