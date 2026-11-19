"""Build the logo contact sheet from the candidate SVGs in ``logo/``.

One row per candidate (``a-*.svg`` .. ``f-*.svg``, sorted by name). Columns,
left to right: full colour, one-colour, inverted, each at 512, 64 and 16 px
true size, centred in a 512 px cell. No labels: row order is file order and
column order is fixed, because the sheet is a dev artifact and carries no text.

Every SVG is validated first, and the sheet is not written if any fails:
flat 512 viewBox, an ``id="field"`` background, only ink and accent, one
stroke weight, and no gradients, filters, text, fonts, styles or images.

Run: python3 unified-design-system/scripts/make_logo_sheet.py
Exit 0 = sheet written; 1 = no candidates or an invalid SVG.
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from logo_check import ACCENT, INK, PAPER, inverted, on_background, one_colour, render
from PIL import Image

LOGO_DIR = Path(__file__).resolve().parents[1] / "logo"
STROKE = 40  # the one stroke weight every candidate uses, on a 512 canvas
VIEWBOX = "0 0 512 512"
SIZES = (512, 64, 16)
VARIANTS = ("colour", "one-colour", "inverted")
CELL = 512
GAP = 32

BANNED_TAGS = frozenset(
    {
        "linearGradient",
        "radialGradient",
        "filter",
        "text",
        "tspan",
        "textPath",
        "font",
        "font-face",
        "style",
        "image",
        "pattern",
        "mask",
        "foreignObject",
    }
)
BANNED_ATTRS = frozenset({"filter", "style", "font-family", "font", "class"})
ALLOWED_PAINT = frozenset({INK.lower(), ACCENT.lower(), "none"})

_STROKE_RE = re.compile(r'stroke-width="([^"]+)"')


def _local(name: str) -> str:
    """Strip an ``{namespace}`` prefix from an element or attribute name."""
    return name.rsplit("}", 1)[-1]


def candidates(directory: Path) -> list[Path]:
    """Candidate SVGs, sorted by file name (a..f)."""
    return sorted(directory.glob("*.svg"))


def stroke_widths(svg_text: str) -> set[str]:
    """Every distinct ``stroke-width`` value in the SVG."""
    return set(_STROKE_RE.findall(svg_text))


def problems(svg_text: str) -> list[str]:
    """Reasons the SVG breaks the flat-logo rules; empty when it is valid."""
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError as exc:
        return [f"not XML: {exc}"]
    found: list[str] = []
    if root.get("viewBox") != VIEWBOX:
        found.append(f"viewBox must be {VIEWBOX!r}")
    if not any(el.get("id") == "field" for el in root.iter()):
        found.append('no id="field" background')
    for el in root.iter():
        tag = _local(el.tag)
        if tag in BANNED_TAGS:
            found.append(f"banned element <{tag}>")
        for attr, value in el.attrib.items():
            name = _local(attr)
            if name in BANNED_ATTRS:
                found.append(f"banned attribute {name} on <{tag}>")
            if name in {"fill", "stroke"} and value.lower() not in ALLOWED_PAINT:
                found.append(f"{name}={value!r} on <{tag}> is not ink or accent")
    widths = stroke_widths(svg_text) - {str(STROKE)}
    if widths:
        found.append(f"stroke-width {sorted(widths)} is not {STROKE}")
    return found


def variant_text(svg_text: str, variant: str) -> str:
    """The SVG source for one column variant."""
    if variant == "one-colour":
        return one_colour(svg_text)
    if variant == "inverted":
        return inverted(svg_text)
    return svg_text


def build_sheet(svgs: list[Path]) -> Image.Image:
    """Render every candidate in every variant and size into one image."""
    cols = len(VARIANTS) * len(SIZES)
    width = cols * CELL + (cols + 1) * GAP
    height = len(svgs) * CELL + (len(svgs) + 1) * GAP
    sheet = Image.new("RGB", (width, height), PAPER)
    for row, svg in enumerate(svgs):
        source = svg.read_text()
        top = GAP + row * (CELL + GAP)
        for v, variant in enumerate(VARIANTS):
            text = variant_text(source, variant)
            for s, size in enumerate(SIZES):
                left = GAP + (v * len(SIZES) + s) * (CELL + GAP)
                offset = (CELL - size) // 2
                image = on_background(render(text, size), PAPER)
                sheet.paste(image, (left + offset, top + offset))
    return sheet


def main(argv: list[str] | None = None) -> int:
    """Validate the candidates, then write the contact sheet PNG."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", type=Path, default=LOGO_DIR)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    svgs = candidates(args.dir)
    if not svgs:
        print(f"make_logo_sheet: no SVGs in {args.dir}", file=sys.stderr)
        return 1
    bad = {svg.name: problems(svg.read_text()) for svg in svgs}
    bad = {name: found for name, found in bad.items() if found}
    for name, found in bad.items():
        for problem in found:
            print(f"make_logo_sheet: {name}: {problem}", file=sys.stderr)
    if bad:
        return 1
    out: Path = args.out or args.dir / "contact-sheet.png"
    build_sheet(svgs).save(out, optimize=True)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
