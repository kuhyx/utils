"""Screen-height-derived compaction for the design-system type/space scales.

The token scales in :class:`~gatelock._window.LockConfig` are authored in
pixels, and every screen in every app fits a 1366x768 panel at full size --
which is checked, per app, by ``scripts/verify_screen_fits.py``. So 768px and
up is *not* compacted: shrinking type a screen has room for buys nothing.

Below 768px there is no such evidence, and a lock surface cannot solve
"content taller than the screen" by scrolling -- it is a full-screen, grabbed
window whose whole job is to present one screen's worth of decision. There the
scale is compacted as a best-effort so those panels degrade gracefully rather
than hiding a submit button.

This module resolves one process-wide factor from the display height and
applies it inside ``type_px()``/``space()``, which is what lets it reach the
module-level ``LockConfig()`` constants the apps build at import time, before
any Tk root exists.

The factor is deliberately *not* a continuous function of height: two
breakpoints keep the rendering predictable and testable, and keep every
supported screen looking exactly as the design system specifies.
"""

from __future__ import annotations

from contextlib import contextmanager
import logging
import os
import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

_logger = logging.getLogger(__name__)

# Set to a float to force a factor -- used by the fit-check harness to render a
# target resolution's layout on whatever display it happens to run on, and
# available as a user escape hatch.
ENV_OVERRIDE = "GATELOCK_UI_DENSITY"

# (minimum screen height, factor). First match wins, tallest first.
# 768 and up is verified to fit at full size, so it is never compacted.
# Anything shorter is best-effort: compacted, but not covered by any app's
# fit check.
_BREAKPOINTS: tuple[tuple[int, float], ...] = (
    (768, 1.0),
    (0, 0.7),
)

# Nothing may shrink below these, whatever the factor says: text stops being
# readable and touching gaps stop reading as separation.
_MIN_TYPE_PX = 11
_MIN_SPACE_PX = 2

# One-slot cache. A dict rather than a module global with ``global`` writes,
# so the module has no rebindable state and needs no lint escape hatch.
_cache: dict[str, float] = {}


def factor_for_height(height_px: int) -> float:
    """Return the compaction factor for a display of ``height_px``."""
    for minimum, factor in _BREAKPOINTS:
        if height_px >= minimum:
            return factor
    # Unreachable: the last breakpoint matches every non-negative height. A
    # negative height means Tk reported nonsense; treat it as "do not compact"
    # rather than silently picking the smallest scale.
    _logger.warning(
        "screen height %dpx is not a real height; leaving the type scale uncompacted",
        height_px,
    )
    return 1.0


def _usable_height(raw: object) -> int | None:
    """Return ``raw`` if it is a real pixel height, else None with a warning.

    Deliberately a type check rather than ``int(raw)`` in a ``try``: the
    consuming apps replace the whole ``tkinter`` module with a fake in their
    test suites, so ``winfo_screenheight()`` can return a mock that neither
    converts nor raises anything catchable -- and an ``except`` clause naming
    a mocked ``tk.TclError`` is itself a TypeError.
    """
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    _logger.warning(
        "screen height came back as %r, not a number; the type scale stays "
        "uncompacted, which can overflow a short screen",
        raw,
    )
    return None


def _screen_height() -> int | None:
    """Return the display height in px, or None when there is no display."""
    root = getattr(tk, "_default_root", None)
    if root is not None:
        return _usable_height(root.winfo_screenheight())
    try:
        probe = tk.Tk()
    except tk.TclError as exc:
        _logger.warning(
            "no display available to size the type scale (%s); leaving it "
            "uncompacted -- expected in headless tests, a bug anywhere else",
            exc,
        )
        return None
    try:
        return _usable_height(probe.winfo_screenheight())
    finally:
        probe.destroy()


def density() -> float:
    """Return the process-wide compaction factor, resolving it once.

    Cached because it is read for every font and every pad on every repaint,
    and because a lock surface's display cannot change under it without the
    surfaces being rebuilt anyway.
    """
    cached = _cache.get("factor")
    if cached is not None:
        return cached
    override = _forced_factor()
    if override is not None:
        _cache["factor"] = override
        _logger.info("type scale forced to %.2f by %s", override, ENV_OVERRIDE)
        return override
    height = _screen_height()
    factor = 1.0 if height is None else factor_for_height(height)
    _cache["factor"] = factor
    if factor != 1.0:
        _logger.info(
            "compacting the type/space scale to %.2f for a %dpx screen",
            factor,
            height,
        )
    return factor


def _forced_factor() -> float | None:
    """Return the env-forced factor, or None when unset or unusable."""
    override = os.environ.get(ENV_OVERRIDE)
    if not override:
        return None
    try:
        return float(override)
    except ValueError:
        _logger.warning(
            "%s=%r is not a number; ignoring it and sizing from the screen instead",
            ENV_OVERRIDE,
            override,
        )
        return None


def reset_cache() -> None:
    """Forget the resolved factor. For tests and the fit-check harness."""
    _cache.clear()


def scale_type(px: int) -> int:
    """Compact a type-scale value, never below :data:`_MIN_TYPE_PX`."""
    return max(_MIN_TYPE_PX, round(px * density()))


def scale_space(px: int) -> int:
    """Compact a spacing value, never below :data:`_MIN_SPACE_PX`.

    A zero stays zero: "no gap" is a deliberate choice, not a small gap.
    """
    if px <= 0:
        return px
    return max(_MIN_SPACE_PX, round(px * density()))


@contextmanager
def forced(factor: float) -> Iterator[None]:
    """Force the compaction factor for the duration of the block.

    For the fit-check harness and tests: it lets a 1080p workstation render
    exactly what a 768px panel would, which is the whole point of checking
    the fit somewhere other than the target machine.
    """
    previous = os.environ.get(ENV_OVERRIDE)
    os.environ[ENV_OVERRIDE] = str(factor)
    reset_cache()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(ENV_OVERRIDE, None)
        else:
            os.environ[ENV_OVERRIDE] = previous
        reset_cache()
