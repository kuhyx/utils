# Copyright (c) 2026 Krzysztof Rudnicki
from dataclasses import replace
from typing import TYPE_CHECKING
import wave

from music_theory import manifest, sfx, sfx_presets, sfx_render, wav

if TYPE_CHECKING:
    from pathlib import Path


def _rate(path: Path) -> int:
    with wave.Wave_read(str(path)) as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        return handle.getframerate()


def test_render_all_writes_every_preset_and_a_manifest(tmp_path: Path) -> None:
    entries = sfx_render.render_all(tmp_path)
    wavs = sorted(p.name for p in tmp_path.glob("*.wav"))
    assert wavs == sorted(f"{name}.wav" for name in sfx_presets.NAMES)
    stored = manifest.read(tmp_path / sfx_render.MANIFEST_NAME)
    assert stored == entries
    for name in wavs:
        assert stored[name]["sha256"] == wav.sha256(tmp_path / name)
        assert stored[name]["sample_rate"] == 44100
        assert _rate(tmp_path / name) == 44100


def test_render_all_is_byte_identical_twice(tmp_path: Path) -> None:
    first = sfx_render.render_all(tmp_path / "a")
    second = sfx_render.render_all(tmp_path / "b")
    assert {k: v["sha256"] for k, v in first.items()} == {
        k: v["sha256"] for k, v in second.items()
    }
    for name in first:
        assert (tmp_path / "a" / name).read_bytes() == (
            tmp_path / "b" / name
        ).read_bytes()


def test_a_new_seed_changes_a_noise_preset(tmp_path: Path) -> None:
    preset = sfx_presets.preset("fire_impact")
    one = wav.write(tmp_path / "one.wav", sfx.render(preset), preset.sample_rate)
    other = replace(preset, seed=preset.seed + 1)
    two = wav.write(tmp_path / "two.wav", sfx.render(other), other.sample_rate)
    assert wav.sha256(one) != wav.sha256(two)


def test_subset_at_22050_merges_into_the_manifest(tmp_path: Path) -> None:
    sfx_render.render_all(tmp_path, 22050, ["dodge"])
    entries = sfx_render.render_all(tmp_path, 22050, ["fizzle"])
    assert set(entries) == {"dodge.wav", "fizzle.wav"}
    assert _rate(tmp_path / "fizzle.wav") == 22050
    recipe = entries["fizzle.wav"]["recipe"]
    assert isinstance(recipe, dict)
    assert recipe["sample_rate"] == 22050
