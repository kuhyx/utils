# Copyright (c) 2026 Krzysztof Rudnicki
from dataclasses import replace
import json
from typing import cast

import numpy as np
import pytest

from music_theory import analysis, envelopes, sfx, sweep

RATE = sfx.SFX_SAMPLE_RATE
FLAT = envelopes.Shape(attack=0.0, hold=0.3, decay=0.0)


def _layer(wave: sfx.Wave = "noise") -> sfx.Layer:
    return sfx.Layer(tone=sfx.Tone(wave=wave), shape=FLAT)


def _one(layer: sfx.Layer, seed: int = 1, rate: int = RATE) -> np.ndarray:
    return sfx.render(sfx.Sfx("t", (layer,), seed=seed, sample_rate=rate))


def test_default_rate_is_cd_quality() -> None:
    assert RATE == 44100


def test_render_is_normalised_to_the_peak_and_sized_by_the_layers() -> None:
    late = replace(_layer(), delay=0.1)
    signal = sfx.render(sfx.Sfx("t", (_layer(), late), peak=0.5))
    assert len(signal) == int(0.1 * RATE) + int(0.3 * RATE)
    assert analysis.peak(signal) == pytest.approx(0.5)


def test_delay_leaves_silence_before_the_layer() -> None:
    signal = _one(replace(_layer(), delay=0.05))
    assert not np.any(signal[: int(0.05 * RATE)])
    assert np.any(signal[int(0.05 * RATE) :])


def test_pink_layer_is_darker_than_white() -> None:
    white = analysis.spectral_centroid(_one(_layer("noise")), RATE)
    pink = analysis.spectral_centroid(_one(_layer("pink")), RATE)
    # Amplitude ~ f^-1/2 puts the centroid at a third of Nyquist, white at half.
    assert pink < white * 0.75


def test_tonal_layer_follows_its_pitch_curve() -> None:
    tone = sfx.Tone(wave="sine", pitch=sweep.Pitch(hz=(300.0, 2400.0)))
    signal = _one(replace(_layer(), tone=tone))
    quarter = len(signal) // 4
    early = analysis.dominant_frequency(signal[:quarter], RATE)
    late = analysis.dominant_frequency(signal[-quarter:], RATE)
    assert late > 2 * early


def test_highpass_layer_drops_the_lows() -> None:
    high = sfx.Filter(kind="highpass", hz=(3000.0,))
    raw = _one(_layer())
    cut = _one(replace(_layer(), filtering=high))
    low_raw = analysis.band_energy(raw, 0.0, 1000.0, RATE)
    low_cut = analysis.band_energy(cut, 0.0, 1000.0, RATE)
    assert low_cut < low_raw / 100


def test_bandpass_breakpoints_sweep_up_then_down() -> None:
    whoosh = sfx.Filter(kind="bandpass", hz=(300.0, 3000.0, 400.0), resonance=4.0)
    signal = _one(replace(_layer(), filtering=whoosh))
    third = len(signal) // 3
    start, middle, end = (
        analysis.spectral_centroid(signal[i * third : (i + 1) * third], RATE)
        for i in range(3)
    )
    assert middle > start
    assert middle > end


def test_bitcrush_quantises_the_layer() -> None:
    crushed = _one(replace(_layer("saw"), grit=sfx.Grit(crush_bits=3.0)))
    assert len(np.unique(crushed)) <= 2**4 + 1


def test_ring_modulation_moves_a_tone() -> None:
    tone = sfx.Tone(wave="sine", pitch=sweep.Pitch(hz=(1000.0,)))
    plain = _one(replace(_layer(), tone=tone))
    ringed = _one(replace(_layer(), tone=tone, grit=sfx.Grit(ring_hz=300.0)))
    assert analysis.dominant_frequency(plain, RATE) == pytest.approx(1000.0, abs=5.0)
    assert analysis.dominant_frequency(ringed, RATE) != pytest.approx(1000.0, abs=50.0)


def test_grains_make_a_crackle_of_mostly_silence() -> None:
    crackle = _one(
        replace(_layer(), grit=sfx.Grit(grain_rate=20.0, grain_seconds=0.002))
    )
    assert float(np.mean(crackle == 0.0)) > 0.8


def test_same_seed_same_samples_new_seed_new_noise() -> None:
    assert np.array_equal(_one(_layer(), seed=4), _one(_layer(), seed=4))
    assert not np.array_equal(_one(_layer(), seed=4), _one(_layer(), seed=5))


def test_layers_get_independent_noise() -> None:
    signal = sfx.render(
        sfx.Sfx("t", (replace(_layer(), gain=1.0), replace(_layer(), gain=-1.0)))
    )
    assert np.any(signal)


def test_sample_rate_option_scales_the_frame_count() -> None:
    assert len(_one(_layer(), rate=22050)) * 2 == len(_one(_layer(), rate=44100))


def test_to_dict_is_json_and_names_every_field() -> None:
    data = sfx.Sfx("zap", (_layer(),), seed=9).to_dict()
    text = json.dumps(data)
    assert '"name": "zap"' in text
    assert data["seed"] == 9
    assert data["sample_rate"] == RATE
    layers = cast("list[dict[str, object]]", data["layers"])
    assert set(layers[0]) == {"tone", "shape", "filtering", "grit", "gain", "delay"}


def test_empty_sound_and_bad_wave() -> None:
    assert sfx.render(sfx.Sfx("none", ())).size == 0
    with pytest.raises(ValueError, match="unknown wave"):
        _one(_layer(cast("sfx.Wave", "organ")))


def test_narrow_pulses_carry_no_dc() -> None:
    pulse = sfx.Tone(wave="square", duty=0.25, pitch=sweep.Pitch(hz=(441.0,)))
    signal = _one(replace(_layer(), tone=pulse))
    assert abs(float(np.mean(signal))) < 0.01
