"""Tiny RGBA PNG encoder for icon fixtures (stdlib only, like the gate)."""

from __future__ import annotations

import math
import struct
import zlib
from collections.abc import Callable
from pathlib import Path

SIG = b"\x89PNG\r\n\x1a\n"
SIZE = 1024
INK = bytes((0xB8, 0x86, 0x2E, 0xFF))
FAINT = bytes((0xB8, 0x86, 0x2E, 0x7F))  # alpha 127: fringe, not ink
CLEAR = bytes(4)


def disk_rows(
    radius: float, cx: float = 512.0, cy: float = 512.0, size: int = SIZE
) -> list[bytes]:
    """RGBA rows of a solid disk; pixel centres within `radius` are inked."""
    rows = []
    for y in range(size):
        dy = y + 0.5 - cy
        if abs(dy) >= radius:
            rows.append(CLEAR * size)
            continue
        half = math.sqrt(radius * radius - dy * dy)
        x0 = max(0, math.ceil(cx - half - 0.5))
        x1 = min(size, math.floor(cx + half - 0.5) + 1)
        rows.append(CLEAR * x0 + INK * (x1 - x0) + CLEAR * (size - x1))
    return rows


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _filter(kind: int, row: bytes, prior: bytes) -> bytes:
    """Apply PNG filter `kind` (0-4, 4 bytes per pixel) to one raw row."""
    if kind == 0:
        return row
    out = bytearray(len(row))
    for i, value in enumerate(row):
        a = row[i - 4] if i >= 4 else 0
        b = prior[i]
        c = prior[i - 4] if i >= 4 else 0
        pred = (0, a, b, (a + b) // 2, _paeth(a, b, c))[kind]
        out[i] = (value - pred) & 255
    return bytes(out)


def chunk(kind: bytes, body: bytes) -> bytes:
    """One PNG chunk: length, type, body, CRC."""
    crc = struct.pack(">I", zlib.crc32(kind + body))
    return struct.pack(">I", len(body)) + kind + body + crc


def encode(
    rows: list[bytes],
    *,
    filters: Callable[[int], int] | None = None,
    size: int = SIZE,
    depth: int = 8,
    colour: int = 6,
    interlace: int = 0,
    iend: bool = True,
) -> bytes:
    """PNG bytes for `rows`; `filters(y)` picks each row's filter type."""
    prior = bytes(len(rows[0]))
    raw = bytearray()
    for y, row in enumerate(rows):
        kind = filters(y) if filters else 0
        raw.append(kind)
        raw += _filter(kind, row, prior)
        prior = row
    ihdr = struct.pack(">IIBBBBB", size, size, depth, colour, 0, 0, interlace)
    body = chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw), 1))
    return SIG + body + (chunk(b"IEND", b"") if iend else b"")


def write_icon(
    path: Path, radius: float = 340, cx: float = 512, cy: float = 512
) -> Path:
    """Write a disk icon foreground to `path` (parents created)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode(disk_rows(radius, cx, cy)))
    return path
