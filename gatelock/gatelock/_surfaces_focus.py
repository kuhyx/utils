# Copyright (c) 2026 Krzysztof Rudnicki
"""Which surface takes keyboard focus, and moving it there.

Split from ``_surfaces.py`` (250-line cap). Focus is a read-then-point
concern: it selects among surfaces that already exist and never creates,
moves or destroys one, so it sits outside the structural-change containment
that ``_surfaces`` module docstring describes -- and the static invariant in
``test_recovery_invariants.py`` globs ``_surfaces*.py``, so this sibling is
covered by that guard the moment it exists, with no list to extend.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from gatelock._placement import _Surface
    from gatelock._surface_types import SurfaceInfo


def focus_surface(surfaces: Mapping[str, _Surface], index: int) -> SurfaceInfo | None:
    """Move keyboard focus to the surface at ``index``, returning what got it."""
    for surface in surfaces.values():
        if surface.info.index == index:
            surface.window.focus_force()
            return surface.info
    return None


def preferred_focus_index(surfaces: Mapping[str, _Surface]) -> int:
    """Index of the surface that should take initial focus.

    The live primary output if there is one, else the first surface.
    """
    for surface in surfaces.values():
        if surface.info.is_primary:
            return surface.info.index
    return 0
