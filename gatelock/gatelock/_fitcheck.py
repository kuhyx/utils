"""Measure whether a lock screen fits its surface, at a chosen resolution.

A lock surface is fullscreen, grabbed and (on the production path) VT-locked:
whatever does not fit is content the user cannot reach except by scrolling a
screen that should never have needed scrolling. :meth:`ScrollableSurface.
finalize` reports overflow at runtime; this module is the half that runs
*before* shipping, so a consuming app can assert in CI that every one of its
screens fits on the smallest display it supports.

Usage from an app's ``scripts/verify_screen_fits.py``::

    from gatelock import measure_fit

    result = measure_fit("retry", paint_retry, width=1366, height=768)
    if not result.fits:
        ...

The measurement runs against real Tk on a real (throwaway) display -- widget
heights depend on the font engine, so nothing short of rendering can answer
this honestly.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import tkinter as tk
from typing import TYPE_CHECKING

from gatelock import _density
from gatelock._scrollable import ScrollableSurface
from gatelock._window import LockConfig

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FitResult:
    """What one screen measured at one resolution."""

    name: str
    width: int
    height: int
    content_px: int
    viewport_px: int

    @property
    def overflow_px(self) -> int:
        """Pixels of content past the bottom of the viewport (0 when it fits)."""
        return max(0, self.content_px - self.viewport_px)

    @property
    def fits(self) -> bool:
        """Whether the whole screen is visible without scrolling."""
        return self.overflow_px == 0

    def describe(self) -> str:
        """One line for a verification script's output."""
        verdict = "fits" if self.fits else f"OVERFLOWS by {self.overflow_px}px"
        return (
            f"{self.name} @ {self.width}x{self.height}: "
            f"{self.content_px}px in {self.viewport_px}px -- {verdict}"
        )


def measure_fit(
    name: str,
    build: Callable[[ScrollableSurface], tk.Misc | None],
    *,
    width: int,
    height: int,
    config: LockConfig | None = None,
) -> FitResult:
    """Build one screen at ``width``x``height`` and measure its height.

    The type/space scale is forced to whatever a display of ``height`` would
    resolve to, so the result is what the target machine renders rather than
    what the machine running the check renders.

    Args:
        name: Screen name, for the report.
        build: Paints the screen. Receives the surface; build into
            ``surface.content``. May return the widget whose height *is* the
            screen's height -- needed for a layout that ``place``s a centred
            frame, since ``place`` does not propagate a child's size to its
            parent and the parent would otherwise measure as empty.
        width: Surface width in px.
        height: Surface height in px.
        config: Token source. Defaults to a stock :class:`LockConfig`.

    Returns:
        The measurement. Never raises for a screen that merely overflows --
        overflow is the thing being reported, not an error.
    """
    with _density.forced(_density.factor_for_height(height)):
        return _measure(name, build, width, height, config)


def _measure(
    name: str,
    build: Callable[[ScrollableSurface], tk.Misc | None],
    width: int,
    height: int,
    config: LockConfig | None,
) -> FitResult:
    """Render the screen once and read its height back."""
    root = tk.Tk()
    try:
        # A managed window has its geometry rewritten wholesale by a real
        # window manager -- confirmed under i3, which tiled this to the pane
        # size instead of the requested width/height, silently measuring the
        # wrong resolution. Production lock windows are overrideredirect for
        # exactly this reason; the throwaway root here must match so the
        # measurement is honest regardless of what WM is running the check.
        root.overrideredirect(boolean=True)
        root.geometry(f"{width}x{height}+0+0")
        root.update_idletasks()
        surface = ScrollableSurface(root, config or LockConfig(), center_when_fits=True)
        surface.container.place(relx=0, rely=0, relwidth=1, relheight=1)
        root.update()
        measured = build(surface)
        surface.finalize()
        root.update()
        return FitResult(
            name=name,
            width=width,
            height=height,
            content_px=(measured or surface.content).winfo_reqheight(),
            viewport_px=surface.canvas.winfo_height(),
        )
    finally:
        root.destroy()


def report_fit(results: list[FitResult]) -> bool:
    """Log every measurement and return whether all of them fit."""
    for result in sorted(results, key=lambda r: (-r.overflow_px, r.name)):
        if result.fits:
            _logger.info("  %s", result.describe())
        else:
            _logger.error("  %s", result.describe())
    return all(result.fits for result in results)
