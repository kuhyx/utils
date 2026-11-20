"""Parse the M1 logo SVG into flat polygons every stack can draw.

The art is a square field rect plus filled paths built only from absolute
M/L/Z commands. Each subpath becomes one polygon. The parser refuses anything
else (curves, relative commands) and refuses subpaths whose bounding boxes
overlap: an overlap could be a hole, which a plain polygon fill would paint
over. If the art ever gains a hole, generation fails loudly instead of
shipping a wrong logo.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

_NS = "{http://www.w3.org/2000/svg}"
_TOKEN = re.compile(r"[A-Za-z]|-?(?:\d+(?:\.\d*)?|\.\d+)")
_SEPARATORS = re.compile(r"[\s,]*")


@dataclass(frozen=True)
class Shape:
    """One filled polygon: its colour and flat x, y, x, y, ... points."""

    fill: str
    points: tuple[float, ...]


@dataclass(frozen=True)
class Logo:
    """The logo as a square size, a field colour and polygons on top."""

    size: int
    field: str
    shapes: tuple[Shape, ...]


def _subpaths(d: str) -> list[list[float]]:
    """Split path data into point lists, one per M ... Z subpath."""
    if _SEPARATORS.fullmatch(_TOKEN.sub(" ", d)) is None:
        msg = f"unparsed characters in path data: {_TOKEN.sub('', d)!r}"
        raise ValueError(msg)
    out: list[list[float]] = []
    current: list[float] = []
    for tok in _TOKEN.findall(d):
        if tok in {"M", "L"}:
            continue
        if tok == "Z":
            out.append(current)
            current = []
        elif tok[0].isalpha():
            msg = f"unsupported path command {tok!r}: only M, L and Z"
            raise ValueError(msg)
        else:
            current.append(float(tok))
    if current:
        msg = "path data ends without Z: an open subpath would be dropped"
        raise ValueError(msg)
    return out


def _bbox(points: list[float]) -> tuple[float, float, float, float]:
    xs, ys = points[0::2], points[1::2]
    return min(xs), min(ys), max(xs), max(ys)


def _check_disjoint(polys: list[list[float]]) -> None:
    boxes = [_bbox(p) for p in polys]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                msg = "logo subpaths overlap: a hole needs a real path renderer"
                raise ValueError(msg)


def parse_logo(text: str) -> Logo:
    """Parse the SVG text into a :class:`Logo`."""
    root = ET.fromstring(text)  # noqa: S314 - our own checked-in art
    if any("transform" in el.attrib for el in root.iter()):
        msg = "transform attributes are unsupported: bake them into the path data"
        raise ValueError(msg)
    size = int(float(root.attrib["viewBox"].split()[2]))
    field = next((r for r in root.iter(f"{_NS}rect") if r.get("id") == "field"), None)
    field = field if field is not None else root.find("rect[@id='field']")
    if field is None:
        msg = "logo has no rect id=field"
        raise ValueError(msg)
    shapes: list[Shape] = []
    polys: list[list[float]] = []
    for path in [*root.iter(f"{_NS}path"), *root.iter("path")]:
        for poly in _subpaths(path.attrib["d"]):
            shapes.append(Shape(path.attrib["fill"], tuple(poly)))
            polys.append(poly)
    _check_disjoint(polys)
    return Logo(size, field.attrib["fill"], tuple(shapes))
