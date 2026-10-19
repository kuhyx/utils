# Copyright (c) 2026 Krzysztof Rudnicki
import hashlib

import numpy as np
import pytest

from music_theory import analysis, sfx, sfx_presets, synth

RATE = sfx.SFX_SAMPLE_RATE
ELEMENTS = ("arcane", "fire", "water", "lightning", "earth", "wind")
MOVES = ("dodge", "parry_perfect", "parry_normal", "fizzle")


@pytest.fixture(scope="module")
def rendered() -> dict[str, np.ndarray]:
    return {name: sfx.render(p) for name, p in sfx_presets.PRESETS.items()}


def _halves(signal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    half = len(signal) // 2
    return signal[:half], signal[half:]


def test_the_preset_list_is_exactly_spellcodes_set() -> None:
    expected = {f"{e}_{beat}" for e in ELEMENTS for beat in ("cast", "hit", "impact")}
    expected |= set(MOVES)
    assert set(sfx_presets.NAMES) == expected
    assert len(sfx_presets.NAMES) == 22
    assert sfx_presets.ELEMENTS == ELEMENTS


def test_preset_lookup() -> None:
    assert sfx_presets.preset("fire_hit").name == "fire_hit"
    with pytest.raises(KeyError, match="unknown preset 'frost_hit'"):
        sfx_presets.preset("frost_hit")


def test_every_preset_is_audible_finite_and_short(
    rendered: dict[str, np.ndarray],
) -> None:
    for name, signal in rendered.items():
        assert np.all(np.isfinite(signal)), name
        assert analysis.peak(signal) == pytest.approx(sfx_presets.preset(name).peak), (
            name
        )
        assert 0.08 <= len(signal) / RATE <= 1.5, name


def test_presets_differ_from_each_other(rendered: dict[str, np.ndarray]) -> None:
    digests = {
        hashlib.sha256(synth.to_int16(s).tobytes()).hexdigest()
        for s in rendered.values()
    }
    assert len(digests) == len(rendered)
    seeds = {p.seed for p in sfx_presets.PRESETS.values()}
    assert len(seeds) == len(rendered)


def test_impacts_outlast_hits(rendered: dict[str, np.ndarray]) -> None:
    for element in ELEMENTS:
        assert len(rendered[f"{element}_impact"]) > len(rendered[f"{element}_hit"])


def test_earth_is_darker_than_lightning(rendered: dict[str, np.ndarray]) -> None:
    for beat in ("hit", "impact"):
        earth = analysis.spectral_centroid(rendered[f"earth_{beat}"], RATE)
        lightning = analysis.spectral_centroid(rendered[f"lightning_{beat}"], RATE)
        assert earth < lightning / 2, beat


@pytest.mark.parametrize("name", ["fire_cast", "wind_cast", "water_cast"])
def test_noise_casts_brighten_as_they_charge(
    rendered: dict[str, np.ndarray], name: str
) -> None:
    early, late = _halves(rendered[name])
    assert analysis.spectral_centroid(late, RATE) > analysis.spectral_centroid(
        early, RATE
    )


@pytest.mark.parametrize("name", ["arcane_cast", "lightning_cast", "earth_cast"])
def test_tonal_casts_rise_in_pitch(rendered: dict[str, np.ndarray], name: str) -> None:
    early, late = _halves(rendered[name])
    assert analysis.dominant_frequency(late, RATE) > analysis.dominant_frequency(
        early, RATE
    )


def test_fizzle_falls_and_perfect_parry_rings_higher(
    rendered: dict[str, np.ndarray],
) -> None:
    early, late = _halves(rendered["fizzle"])
    assert analysis.dominant_frequency(late, RATE) < analysis.dominant_frequency(
        early, RATE
    )
    perfect = analysis.dominant_frequency(rendered["parry_perfect"], RATE)
    normal = analysis.dominant_frequency(rendered["parry_normal"], RATE)
    assert perfect > normal
    assert len(rendered["parry_perfect"]) > len(rendered["parry_normal"])


def test_wind_hit_whooshes_up_then_down(rendered: dict[str, np.ndarray]) -> None:
    signal = rendered["wind_hit"]
    third = len(signal) // 3
    start, middle, end = (
        analysis.spectral_centroid(signal[i * third : (i + 1) * third], RATE)
        for i in range(3)
    )
    assert middle > start
    assert middle > end
