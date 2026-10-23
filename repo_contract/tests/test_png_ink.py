"""The stdlib PNG reader and the family ink-circle rule (rule 4)."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

from repo_contract import png_ink

from .pngkit import CLEAR, FAINT, SIG, SIZE, chunk, disk_rows, encode, write_icon


def geometry(tmp_path: Path, data: bytes) -> tuple[float, float, float]:
    path = tmp_path / "icon.png"
    path.write_bytes(data)
    return png_ink.ink_geometry(path)


def test_family_disk_measures_340_centred(tmp_path: Path) -> None:
    radius, cx, cy = png_ink.ink_geometry(write_icon(tmp_path / "i.png"))
    assert (cx, cy) == (512, 512)
    assert 338 < radius <= 340


def test_family_icon_passes(tmp_path: Path) -> None:
    assert png_ink.icon_problems(write_icon(tmp_path / "i.png"), "i.png") == []


@pytest.mark.parametrize("radius", [380, 300])
def test_too_big_or_too_small_fails(tmp_path: Path, radius: int) -> None:
    got = png_ink.icon_problems(write_icon(tmp_path / "i.png", radius), "i.png")
    assert len(got) == 1
    assert got[0].startswith("i.png: ink radius ")
    assert "340px" in got[0] and "app_icons" in got[0]


def test_within_one_percent_passes(tmp_path: Path) -> None:
    assert png_ink.icon_problems(write_icon(tmp_path / "i.png", 349), "i.png") == []


def test_off_centre_fails(tmp_path: Path) -> None:
    path = write_icon(tmp_path / "i.png", 340, cx=520)
    got = png_ink.icon_problems(path, "i.png")
    assert got == [
        "i.png: ink centre (520.0, 512.0) is 8.0px from (512, 512); at most 2px"
    ]


def test_two_px_off_centre_passes(tmp_path: Path) -> None:
    path = write_icon(tmp_path / "i.png", 340, cx=514)
    assert png_ink.icon_problems(path, "i.png") == []


def test_every_filter_type_decodes_identically(tmp_path: Path) -> None:
    rows = disk_rows(100, 500, 520)
    plain = geometry(tmp_path, encode(rows))
    mixed = encode(rows, filters=lambda y: y % 5 if 400 <= y < 640 else 0)
    assert geometry(tmp_path, mixed) == plain


def test_faint_fringe_is_not_ink(tmp_path: Path) -> None:
    rows = disk_rows(100)
    rows[0] = FAINT * SIZE
    assert geometry(tmp_path, encode(rows)) == geometry(
        tmp_path, encode(disk_rows(100))
    )


def test_missing_iend_still_decodes(tmp_path: Path) -> None:
    assert geometry(tmp_path, encode(disk_rows(50), iend=False))[0] > 0


def test_ancillary_chunks_skipped(tmp_path: Path) -> None:
    data = encode(disk_rows(50))
    with_text = data[:33] + chunk(b"tEXt", b"k\0v") + data[33:]
    assert geometry(tmp_path, with_text) == geometry(tmp_path, data)


def _ihdr_only(ihdr: bytes) -> bytes:
    return SIG + chunk(b"IHDR", ihdr) + chunk(b"IEND", b"")


def _header(size: int = SIZE, depth: int = 8, colour: int = 6, il: int = 0) -> bytes:
    return struct.pack(">IIBBBBB", size, size, depth, colour, 0, 0, il)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"GIF89a", "is not a PNG"),
        (SIG + chunk(b"IEND", b""), "has no IHDR chunk"),
        (_ihdr_only(_header(size=512)), "is 512x512; the family canvas is 1024x1024"),
        (_ihdr_only(_header(colour=2)), "must be 8-bit RGBA, non-interlaced"),
        (_ihdr_only(_header(depth=16)), "must be 8-bit RGBA, non-interlaced"),
        (_ihdr_only(_header(il=1)), "must be 8-bit RGBA, non-interlaced"),
        (
            SIG + chunk(b"IHDR", _header()) + chunk(b"IDAT", b"not zlib"),
            "has corrupt image data",
        ),
        (
            SIG + chunk(b"IHDR", _header()) + chunk(b"IDAT", zlib.compress(b"\0" * 9)),
            "has truncated image data",
        ),
        (encode([CLEAR * SIZE] * SIZE), "has no inked pixel (alpha > 127)"),
    ],
)
def test_undecodable_fails_closed(tmp_path: Path, data: bytes, message: str) -> None:
    path = tmp_path / "icon.png"
    path.write_bytes(data)
    got = png_ink.icon_problems(path, "icon.png")
    assert len(got) == 1
    assert got[0].startswith(f"icon.png {message}")


def test_bad_filter_type_fails_closed(tmp_path: Path) -> None:
    raw = (b"\x07" + CLEAR * SIZE) * SIZE
    data = SIG + chunk(b"IHDR", _header()) + chunk(b"IDAT", zlib.compress(raw))
    path = tmp_path / "icon.png"
    path.write_bytes(data)
    assert png_ink.icon_problems(path, "icon.png") == [
        "icon.png has an invalid PNG filter type 7"
    ]


def test_unreadable_file_fails_closed(tmp_path: Path) -> None:
    got = png_ink.icon_problems(tmp_path / "missing.png", "missing.png")
    assert len(got) == 1 and got[0].startswith("missing.png is unreadable:")
