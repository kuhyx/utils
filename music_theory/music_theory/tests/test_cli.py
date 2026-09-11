# Copyright (c) 2026 Krzysztof Rudnicki
import json
import runpy
import sys
from typing import TYPE_CHECKING

import pytest

from music_theory import cli, compose, manifest, wav

if TYPE_CHECKING:
    from pathlib import Path


def test_list_prints_every_demo(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["list"]) == 0
    out = capsys.readouterr().out
    assert "tone" in out
    assert "bracket" in out


def test_explain_prints_facts(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["explain", "comma"]) == 0
    assert "1.013643" in capsys.readouterr().out


def test_demo_writes_numbered_wavs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["demo", "tone", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "01_tone.wav").exists()
    assert "aplay -q" in capsys.readouterr().out


def test_render_writes_wav_and_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recipe_path = tmp_path / "r.json"
    recipe_path.write_text(json.dumps(compose.Recipe(bars=1).to_dict()))
    out = tmp_path / "bed.wav"
    man = tmp_path / "MANIFEST.json"
    args = [
        "render",
        "--recipe",
        str(recipe_path),
        "--out",
        str(out),
        "--manifest",
        str(man),
    ]
    assert cli.main(args) == 0
    entries = manifest.read(man)
    assert entries["bed.wav"]["sha256"] == wav.sha256(out)
    assert cli.main([*args, "--degrade", "1.0"]) == 0
    recipe = manifest.read(man)["bed.wav"]["recipe"]
    assert isinstance(recipe, dict)
    assert recipe["degrade"] == 1.0
    assert "sha256" in capsys.readouterr().out


def test_render_without_manifest(tmp_path: Path) -> None:
    recipe_path = tmp_path / "r.json"
    recipe_path.write_text(json.dumps({"bars": 1}))
    assert (
        cli.main(
            ["render", "--recipe", str(recipe_path), "--out", str(tmp_path / "b.wav")]
        )
        == 0
    )


def test_render_rejects_non_object_recipe(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recipe_path = tmp_path / "r.json"
    recipe_path.write_text("[1]")
    assert (
        cli.main(
            ["render", "--recipe", str(recipe_path), "--out", str(tmp_path / "b.wav")]
        )
        == 1
    )
    assert "error" in capsys.readouterr().out


def test_parser_requires_a_command() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])


def test_module_entry_point(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["music_theory", "list"])
    with pytest.raises(SystemExit) as info:
        runpy.run_module("music_theory", run_name="__main__")
    assert info.value.code == 0
    assert "tone" in capsys.readouterr().out
