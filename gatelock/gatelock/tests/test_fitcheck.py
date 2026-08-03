"""Tests for the pre-ship fit measurement.

This is the harness every consuming app gates its layout on, so it has to be
right about both answers: a screen that fits must not be reported as
overflowing (which would block a good commit) and a screen that overflows must
not be reported as fitting (which is the failure it exists to catch).
"""

from __future__ import annotations

import os
import tkinter as tk

import pytest

from gatelock._fitcheck import FitResult, measure_fit, report_fit

pytestmark = pytest.mark.skipif(
    not os.environ.get("DISPLAY"),
    reason="needs a real X display; run under xvfb-run in a headless checkout",
)

_WIDTH = 400
_HEIGHT = 200


def _short(surface: object) -> None:
    """Paint one label -- comfortably shorter than the viewport."""
    tk.Label(surface.content, text="short").pack()


def _tall(surface: object) -> None:
    """Paint far more rows than the viewport can hold."""
    for index in range(40):
        tk.Label(surface.content, text=f"row {index}").pack()


def _placed(surface: object) -> tk.Misc:
    """Paint into a ``place``d frame and return it, as the lock apps do."""
    frame = tk.Frame(surface.content)
    frame.place(relx=0.5, rely=0.5, anchor="center")
    for index in range(40):
        tk.Label(frame, text=f"row {index}").pack()
    return frame


def test_a_short_screen_fits() -> None:
    """The good case reports zero overflow."""
    result = measure_fit("short", _short, width=_WIDTH, height=_HEIGHT)
    assert result.fits
    assert result.overflow_px == 0
    assert "fits" in result.describe()


def test_a_tall_screen_overflows_by_the_real_amount() -> None:
    """The failing case reports how much did not fit, not just that it did."""
    result = measure_fit("tall", _tall, width=_WIDTH, height=_HEIGHT)
    assert not result.fits
    assert result.overflow_px == result.content_px - result.viewport_px
    assert "OVERFLOWS" in result.describe()


def test_a_placed_frame_is_measured_through_the_returned_widget() -> None:
    """``place`` does not propagate size, so the builder names what to measure.

    Without this the parent measures as empty and every place-centred lock
    screen -- which is most of them outside screen-locker -- would be reported
    as fitting no matter how tall it grew.
    """
    result = measure_fit("placed", _placed, width=_WIDTH, height=_HEIGHT)
    assert not result.fits


def test_report_returns_false_when_anything_overflows() -> None:
    """The report is the gate's verdict, so one bad screen fails the batch."""
    good = FitResult("good", _WIDTH, _HEIGHT, content_px=100, viewport_px=200)
    bad = FitResult("bad", _WIDTH, _HEIGHT, content_px=300, viewport_px=200)
    assert report_fit([good])
    assert not report_fit([good, bad])
    assert report_fit([]) is True
