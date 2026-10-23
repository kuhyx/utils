"""Rule 4: every launcher glyph fills the same circle as the shared generator's.

The shared icon generator (`~/src/testsAndMisc/python_pkg/app_icons`, `fit.py`)
scales each glyph so its furthest inked pixel (alpha > 127) sits exactly
`style.INK_RADIUS` = 340px from the centre of its ink box, on a 1024px canvas,
with that centre on the canvas centre. This module re-measures a committed
`assets/icon/icon_foreground.png` the same way, so a hand-edited or stale
foreground cannot drift back to a different size.

Stdlib only (zlib + struct): the per-repo CI runner installs nothing, so Pillow
is not an option. Only the generator's own output format is decoded (8-bit
RGBA, non-interlaced, 1024x1024); anything else fails closed with a message.
Only the alpha channel is unfiltered: PNG filters work byte-wise with a
one-pixel offset, so alpha bytes depend only on other alpha bytes.
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

CANVAS = 1024
INK_RADIUS = 340  # app_icons style.INK_RADIUS
RADIUS_TOLERANCE = CANVAS * 0.01
CENTRE_TOLERANCE = 2.0
INK_ALPHA = 127  # app_icons fit._INK_ALPHA: above this is ink
_SIG = b"\x89PNG\r\n\x1a\n"
_INKED = bytes(1 if v > INK_ALPHA else 0 for v in range(256))
_FIX = "regenerate it with ~/src/testsAndMisc/python_pkg/app_icons"


class PngError(ValueError):
    """The PNG is not one this check can measure."""


def _chunks(data: bytes) -> tuple[tuple[int, ...], bytes]:
    """(IHDR fields, concatenated IDAT) of a PNG byte string."""
    if not data.startswith(_SIG):
        raise PngError("is not a PNG")
    pos, header, idat = len(_SIG), None, []
    while pos + 8 <= len(data):
        (size,) = struct.unpack_from(">I", data, pos)
        kind, body = data[pos + 4 : pos + 8], data[pos + 8 : pos + 8 + size]
        pos += 12 + size
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
    if header is None:
        raise PngError("has no IHDR chunk")
    return header, b"".join(idat)


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _unfilter(kind: int, cur: bytes, prior: bytes) -> bytes:
    """Undo one row's PNG filter on a single channel (neighbour = 1 byte)."""
    if kind == 0:
        return cur
    if kind == 2:
        return bytes((x + p) & 255 for x, p in zip(cur, prior))
    if kind not in (1, 3, 4):
        raise PngError(f"has an invalid PNG filter type {kind}")
    out = bytearray(cur)
    for i in range(len(out)):
        a = out[i - 1] if i else 0
        if kind == 1:
            pred = a
        elif kind == 3:
            pred = (a + prior[i]) // 2
        else:
            pred = _paeth(a, prior[i], prior[i - 1] if i else 0)
        out[i] = (out[i] + pred) & 255
    return bytes(out)


def alpha_rows(data: bytes) -> list[bytes]:
    """The alpha channel of a 1024x1024 8-bit RGBA PNG, one bytes per row."""
    (width, height, depth, colour, _, _, interlace), idat = _chunks(data)
    if (width, height) != (CANVAS, CANVAS):
        raise PngError(f"is {width}x{height}; the family canvas is {CANVAS}x{CANVAS}")
    if depth != 8 or colour != 6 or interlace:
        raise PngError(
            "must be 8-bit RGBA, non-interlaced "
            f"(bit depth {depth}, colour type {colour}, interlace {interlace})"
        )
    try:
        raw = zlib.decompress(idat)
    except zlib.error as exc:
        raise PngError(f"has corrupt image data: {exc}") from exc
    stride = width * 4 + 1
    if len(raw) != stride * height:
        raise PngError("has truncated image data")
    rows, prior = [], bytes(width)
    for y in range(height):
        line = raw[y * stride : (y + 1) * stride]
        prior = _unfilter(line[0], line[4::4], prior)
        rows.append(prior)
    return rows


def ink_geometry(path: Path) -> tuple[float, float, float]:
    """(radius, cx, cy) exactly as app_icons `fit.ink_geometry` measures it.

    The furthest inked pixel of a row is always its first or last one, so
    only those two are measured per row.
    """
    spans = []
    for y, row in enumerate(alpha_rows(path.read_bytes())):
        mask = row.translate(_INKED)
        first = mask.find(1)
        if first >= 0:
            spans.append((y, first, mask.rfind(1)))
    if not spans:
        raise PngError(f"has no inked pixel (alpha > {INK_ALPHA})")
    cx = (min(s[1] for s in spans) + max(s[2] for s in spans) + 1) / 2
    cy = (spans[0][0] + spans[-1][0] + 1) / 2
    radius = max(
        math.hypot(x + 0.5 - cx, y + 0.5 - cy) for y, *ends in spans for x in ends
    )
    return radius, cx, cy


def icon_problems(path: Path, rel: str) -> list[str]:
    """Violations of the family ink circle for the foreground at `path`."""
    try:
        radius, cx, cy = ink_geometry(path)
    except PngError as exc:
        return [f"{rel} {exc}"]
    except OSError as exc:
        return [f"{rel} is unreadable: {exc}"]
    out = []
    if abs(radius - INK_RADIUS) > RADIUS_TOLERANCE:
        out.append(
            f"{rel}: ink radius {radius:.1f}px, the family circle is {INK_RADIUS}px"
            f" ±{RADIUS_TOLERANCE:.1f}px: {_FIX}"
        )
    off = math.hypot(cx - CANVAS / 2, cy - CANVAS / 2)
    if off > CENTRE_TOLERANCE:
        out.append(
            f"{rel}: ink centre ({cx:.1f}, {cy:.1f}) is {off:.1f}px from"
            f" ({CANVAS // 2}, {CANVAS // 2}); at most {CENTRE_TOLERANCE:.0f}px"
        )
    return out
