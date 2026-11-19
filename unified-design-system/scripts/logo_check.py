"""Render the four logo legibility checks for one SVG into one PNG.

Panels, left to right (order is the only label: the PNG is a dev artifact
and carries no text):

  1. full colour at 16 px, enlarged to 128 px nearest-neighbour
  2. one-colour: field dropped, every mark in ink, on paper
  3. inverted: ink and accent swapped (accent field, ink mark)
  4. squint: 128 px render blurred, reduced to 16 px, enlarged nearest-neighbour

A candidate SVG paints its background as an element with ``id="field"`` and
uses only the palette's ink and accent. Rendering goes through
``rsvg-convert``; compositing through Pillow.

Run: python3 unified-design-system/scripts/logo_check.py <svg> [--out PNG]
Exit 0 = PNG written; 1 = SVG missing or render failed.
"""

from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageFilter

INK = "#211D1B"
ACCENT = "#B8862E"
PAPER = "#F6F4F3"

PANEL = 128  # every panel is shown at this size
SMALL = 16  # favicon-size check
SQUINT = 16  # squint grid: blur, then this many pixels across
SQUINT_BLUR = 6  # Gaussian radius at PANEL size
GAP = 8

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

_INK_RE = re.compile(re.escape(INK), re.IGNORECASE)
_ACCENT_RE = re.compile(re.escape(ACCENT), re.IGNORECASE)


def render(svg_text: str, size: int) -> Image.Image:
    """Rasterise SVG text to a square RGBA image of ``size`` pixels."""
    png = subprocess.run(
        ["rsvg-convert", "-w", str(size), "-h", str(size), "-f", "png"],
        input=svg_text.encode(),
        capture_output=True,
        check=True,
    ).stdout
    return Image.open(io.BytesIO(png)).convert("RGBA")


def on_background(image: Image.Image, colour: str) -> Image.Image:
    """Flatten an RGBA image onto a solid colour, returning RGB."""
    base = Image.new("RGBA", image.size, colour)
    base.alpha_composite(image)
    return base.convert("RGB")


def enlarge(image: Image.Image, size: int = PANEL) -> Image.Image:
    """Scale up with hard pixel edges so small-size artefacts stay visible."""
    return image.resize((size, size), Image.Resampling.NEAREST)


def inverted(svg_text: str) -> str:
    """Swap ink and accent everywhere, so the field turns accent."""
    placeholder = "#__SWAP__"
    text = _INK_RE.sub(placeholder, svg_text)
    text = _ACCENT_RE.sub(INK, text)
    return text.replace(placeholder, ACCENT)


def one_colour(svg_text: str) -> str:
    """Drop the field and paint every mark in ink."""
    root = ET.fromstring(svg_text)
    for parent in root.iter():
        for child in list(parent):
            if child.get("id") == "field":
                parent.remove(child)
    return _ACCENT_RE.sub(INK, ET.tostring(root, encoding="unicode"))


def squint(svg_text: str) -> Image.Image:
    """Blur and coarsen the render, the way the mark reads at a glance."""
    blurred = on_background(render(svg_text, PANEL), PAPER).filter(
        ImageFilter.GaussianBlur(SQUINT_BLUR)
    )
    return blurred.resize((SQUINT, SQUINT), Image.Resampling.BOX)


def panels(svg_text: str) -> list[Image.Image]:
    """The four check panels in their fixed order, each PANEL px square."""
    return [
        enlarge(on_background(render(svg_text, SMALL), PAPER)),
        on_background(render(one_colour(svg_text), PANEL), PAPER),
        on_background(render(inverted(svg_text), PANEL), PAPER),
        enlarge(squint(svg_text)),
    ]


def compose(images: list[Image.Image]) -> Image.Image:
    """Lay the panels out in one row with a paper gutter."""
    width = len(images) * PANEL + (len(images) + 1) * GAP
    sheet = Image.new("RGB", (width, PANEL + 2 * GAP), PAPER)
    for index, image in enumerate(images):
        sheet.paste(image, (GAP + index * (PANEL + GAP), GAP))
    return sheet


def main(argv: list[str] | None = None) -> int:
    """Write ``<svg stem>-check.png`` (or ``--out``) for one candidate SVG."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("svg", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    svg: Path = args.svg
    if not svg.is_file():
        print(f"logo_check: no such file: {svg}", file=sys.stderr)
        return 1
    out: Path = args.out or svg.with_name(f"{svg.stem}-check.png")
    try:
        sheet = compose(panels(svg.read_text()))
    except (subprocess.CalledProcessError, ET.ParseError) as exc:
        print(f"logo_check: cannot render {svg}: {exc}", file=sys.stderr)
        return 1
    sheet.save(out, optimize=True)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
