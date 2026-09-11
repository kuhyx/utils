# Copyright (c) 2026 Krzysztof Rudnicki
import json
from typing import TYPE_CHECKING

import pytest

from music_theory import __version__, compose, manifest, wav

if TYPE_CHECKING:
    from pathlib import Path


def test_entry_records_recipe_version_and_hash(tmp_path: Path) -> None:
    recipe = compose.Recipe(bars=1)
    signal = compose.compose(recipe)
    path = wav.write(tmp_path / "bed.wav", signal, recipe.sample_rate)
    record = manifest.entry(recipe, path, signal)
    assert record["file"] == "bed.wav"
    assert record["music_theory_version"] == __version__
    assert record["sha256"] == wav.sha256(path)
    assert record["frames"] == len(signal)
    assert record["recipe"] == recipe.to_dict()


def test_write_and_read(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "m.json"
    manifest.write(path, {"b": {"x": 1}, "a": {"y": 2}})
    text = path.read_text()
    assert text.endswith("\n")
    assert text.index('"a"') < text.index('"b"')
    assert manifest.read(path) == {"a": {"y": 2}, "b": {"x": 1}}


def test_read_rejects_non_object(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    path.write_text(json.dumps([1, 2]))
    with pytest.raises(TypeError, match="manifest object"):
        manifest.read(path)
