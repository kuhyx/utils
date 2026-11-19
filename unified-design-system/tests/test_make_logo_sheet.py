"""Tests for make_logo_sheet.py: valid flat SVGs in, one contact sheet out."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

Image = pytest.importorskip("PIL.Image")
if shutil.which("rsvg-convert") is None:  # pragma: no cover - env guard
    pytest.skip("rsvg-convert not installed", allow_module_level=True)

import make_logo_sheet

LOGO_DIR = Path(__file__).resolve().parents[1] / "logo"
GOOD = (Path(__file__).parent / "fixtures" / "logo-fixture.svg").read_text()


def test_three_variants_of_six_candidates_exist() -> None:
    names = [p.name[:2] for p in make_logo_sheet.candidates(LOGO_DIR)]
    assert names == [f"{kind}{n}" for kind in "abcdef" for n in "123"]


@pytest.mark.parametrize("svg", sorted(LOGO_DIR.glob("*.svg")), ids=lambda p: p.name)
def test_candidate_is_valid_flat_svg(svg: Path) -> None:
    assert make_logo_sheet.problems(svg.read_text()) == []


def test_one_stroke_weight_across_candidates() -> None:
    widths = {
        w
        for svg in make_logo_sheet.candidates(LOGO_DIR)
        for w in make_logo_sheet.stroke_widths(svg.read_text())
    }
    assert widths == {str(make_logo_sheet.STROKE)}


def test_fixture_is_valid() -> None:
    assert make_logo_sheet.problems(GOOD) == []


@pytest.mark.parametrize(
    ("needle", "replacement"),
    [
        ("<path", '<linearGradient id="g"/><path'),
        ("<path", '<radialGradient id="g"/><path'),
        ("<path", '<filter id="f"/><path'),
        ("<path", "<text>k</text><path"),
        ("<path", '<path font-family="Inter"'),
        ("<path", '<path filter="url(#f)"'),
        ("<path", '<path style="fill:red"'),
        ('stroke="#B8862E"', 'stroke="#FF0000"'),
        ('id="field" ', ""),
        ('viewBox="0 0 512 512"', 'viewBox="0 0 100 100"'),
    ],
)
def test_banned_content_is_reported(needle: str, replacement: str) -> None:
    assert make_logo_sheet.problems(GOOD.replace(needle, replacement, 1))


def test_unparseable_svg_is_reported() -> None:
    assert make_logo_sheet.problems("<svg") != []


def test_main_writes_sheet(tmp_path: Path) -> None:
    out = tmp_path / "sheet.png"
    assert make_logo_sheet.main(["--dir", str(LOGO_DIR), "--out", str(out)]) == 0
    sheet = Image.open(out)
    rows, cols = 18, len(make_logo_sheet.VARIANTS) * len(make_logo_sheet.SIZES)
    cell, gap = make_logo_sheet.CELL, make_logo_sheet.GAP
    assert sheet.size == (
        cols * cell + (cols + 1) * gap,
        rows * cell + (rows + 1) * gap,
    )


def test_main_refuses_invalid_svg(tmp_path: Path) -> None:
    (tmp_path / "a-bad.svg").write_text(GOOD.replace("<path", "<text>k</text><path"))
    assert (
        make_logo_sheet.main(["--dir", str(tmp_path), "--out", str(tmp_path / "s.png")])
        == 1
    )
    assert not (tmp_path / "s.png").exists()


def test_main_refuses_empty_dir(tmp_path: Path) -> None:
    assert (
        make_logo_sheet.main(["--dir", str(tmp_path), "--out", str(tmp_path / "s.png")])
        == 1
    )
