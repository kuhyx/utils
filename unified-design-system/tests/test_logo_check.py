"""Tests for logo_check.py: one PNG, four panels, hard pixel edges, no text."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

Image = pytest.importorskip("PIL.Image")
if shutil.which("rsvg-convert") is None:  # pragma: no cover - env guard
    pytest.skip("rsvg-convert not installed", allow_module_level=True)

import logo_check

FIXTURE = Path(__file__).parent / "fixtures" / "logo-fixture.svg"
INK = (0x21, 0x1D, 0x1B)
ACCENT = (0xB8, 0x86, 0x2E)


def _panel(sheet: Image.Image, index: int) -> Image.Image:
    left = logo_check.GAP + index * (logo_check.PANEL + logo_check.GAP)
    top = logo_check.GAP
    return sheet.crop((left, top, left + logo_check.PANEL, top + logo_check.PANEL))


@pytest.fixture
def sheet(tmp_path: Path) -> Image.Image:
    out = tmp_path / "check.png"
    assert logo_check.main([str(FIXTURE), "--out", str(out)]) == 0
    assert out.is_file()
    return Image.open(out).convert("RGB")


def test_sheet_has_four_panels_side_by_side(sheet: Image.Image) -> None:
    gap, panel = logo_check.GAP, logo_check.PANEL
    assert sheet.size == (4 * panel + 5 * gap, panel + 2 * gap)


def test_small_panel_is_nearest_neighbour_blocks(sheet: Image.Image) -> None:
    """The 16 px render is enlarged 8x with hard edges: every 8x8 block is flat."""
    small = _panel(sheet, 0)
    step = logo_check.PANEL // logo_check.SMALL
    for by in range(logo_check.SMALL):
        for bx in range(logo_check.SMALL):
            block = small.crop((bx * step, by * step, (bx + 1) * step, (by + 1) * step))
            assert len(block.getcolors()) == 1


def test_squint_panel_is_nearest_neighbour_blocks(sheet: Image.Image) -> None:
    squint = _panel(sheet, 3)
    step = logo_check.PANEL // logo_check.SQUINT
    block = squint.crop((0, 0, step, step))
    assert len(block.getcolors()) == 1
    assert len(squint.getcolors(maxcolors=4096)) > 2  # blurred, not flat


def test_one_colour_panel_uses_ink_on_paper_only(sheet: Image.Image) -> None:
    panel = _panel(sheet, 1)
    colours = {c for _, c in panel.getcolors(maxcolors=4096)}
    assert INK in colours
    assert ACCENT not in colours


def test_inverted_panel_swaps_field_and_mark(sheet: Image.Image) -> None:
    panel = _panel(sheet, 2)
    assert panel.getpixel((2, 2)) == ACCENT  # field corner is now accent
    colours = {c for _, c in panel.getcolors(maxcolors=4096)}
    assert INK in colours


def test_default_out_path_sits_next_to_svg(tmp_path: Path) -> None:
    svg = tmp_path / "x.svg"
    svg.write_text(FIXTURE.read_text())
    assert logo_check.main([str(svg)]) == 0
    assert (tmp_path / "x-check.png").is_file()


def test_missing_svg_exits_nonzero(tmp_path: Path) -> None:
    assert logo_check.main([str(tmp_path / "nope.svg")]) == 1
