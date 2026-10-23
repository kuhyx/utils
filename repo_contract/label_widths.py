"""Advance widths of the ASCII letters in the Pixel launcher's label font.

Measured from ``GoogleSansFlex-Regular.ttf`` pulled off kuhy's Pixel 6a
(``/product/fonts``) at a 100px em, rounded. Only the numbers are kept, not
the font, which is not redistributable. Kerning is ignored; on every label
measured it moved the total by under 1%.

Copied verbatim from testsAndMisc `python_pkg/app_icons/_label_widths.py`
(utils must not import another repo); keep the two in step.
"""

from __future__ import annotations

from typing import Final

ADVANCE: Final[dict[str, int]] = {
    "a": 54, "b": 60, "c": 54, "d": 60, "e": 56, "f": 38, "g": 60, "h": 56,
    "i": 23, "j": 23, "k": 50, "l": 21, "m": 88, "n": 56, "o": 60, "p": 60,
    "q": 60, "r": 38, "s": 47, "t": 36, "u": 56, "v": 51, "w": 78, "x": 49,
    "y": 51, "z": 48, "A": 67, "B": 61, "C": 74, "D": 70, "E": 55, "F": 53,
    "G": 79, "H": 70, "I": 24, "J": 53, "K": 63, "L": 51, "M": 87, "N": 71,
    "O": 82, "P": 58, "Q": 82, "R": 59, "S": 55, "T": 54, "U": 65, "V": 63,
    "W": 94, "X": 64, "Y": 60, "Z": 57,
}  # fmt: skip

# The widest label seen whole in the app drawer is WakeAlarm (522), and
# FocusOwner (580) lost its last letters there (kuhy, 2026-10-23).
MAX_WIDTH: Final[int] = 522


def label_width(name: str) -> int:
    """Return a label's width in font units; only call on ASCII letters."""
    return sum(ADVANCE[char] for char in name)
