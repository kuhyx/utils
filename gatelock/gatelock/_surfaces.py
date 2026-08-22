"""Own every lock window: one per live output, plus the backdrop.

This is the **only** module allowed to create, move or destroy windows. That
containment is what lets :mod:`gatelock._recovery` be provably monotonic --
recovery delegates all structural change here and therefore cannot itself
contain a teardown path. A test asserts that separation by parsing both
modules, so routing destruction back into recovery fails CI.

The window shape, and why:

.. code-block:: text

    GateRoot (tk.Tk)              <- always the grab holder, always mapped
      |- overrideredirect, geometry = the whole X screen, no widgets
      |- Toplevel  -> "DP-0"    3840x2160+0+0
      +- Toplevel  -> "HDMI-0"  2560x1440+3840+0

Three probe results against a live X server dictated this and are worth
recording, because each rules out an approach that looks reasonable:

1. **A Tk grab must live on the root**, not on a Toplevel. With the grab on a
   *sibling* Toplevel, clicks on another surface are swallowed. Grabbing
   surface 0 would leave surface 1 visible but dead -- the 2026-07-25 incident
   rebuilt on purpose.
2. **``overrideredirect`` must be set before the window is mapped.** Set it
   afterwards and the placement is ignored.
3. **A window-manager-managed toplevel cannot be placed per-output** -- i3
   rewrites the geometry wholesale. Per-output placement *requires*
   override-redirect, so ``attributes(fullscreen=True)`` is gone from the lock
   path entirely: it is an EWMH request that an override-redirect window is
   invisible to, and where it does apply it targets one monitor or the whole
   bounding box. Neither is what per-output locking needs.
"""

from __future__ import annotations

import logging
import tkinter as tk
from typing import TYPE_CHECKING

from gatelock._placement import (
    _Surface,
    blind_outputs,
    needs_backdrop_root,
    enforce_all,
    set_geometry,
)
from gatelock._surface_types import (
    SurfaceBuilder,
    SurfaceDelta,
    SurfaceInfo,
)
from gatelock._textmirror import TextMirror, mirror_text_widgets

# Names this module re-exports after the 250-line split. Listed explicitly so
# the autofixer cannot prune an import that exists *for* its re-export -- it
# stripped mirror_text_widgets once, and `gatelock` itself stopped importing.
__all__ = [
    "SurfaceBuilder",
    "SurfaceDelta",
    "SurfaceInfo",
    "SurfaceSet",
    "TextMirror",
    "mirror_text_widgets",
    "needs_backdrop_root",
]

if TYPE_CHECKING:
    from gatelock._outputs import OutputScan
    from gatelock._window import LockConfig

_logger = logging.getLogger(__name__)

# Tk's attributes() takes the value positionally, so a bare `True` here
# trips the boolean-positional lint. Naming it satisfies both that rule
# and the type stubs, which have no keyword overload.
_TOPMOST_ON = True


class SurfaceSet:
    """The full set of lock windows, kept in step with the live outputs."""

    def __init__(
        self,
        root: tk.Tk,
        config: LockConfig,
        builder: SurfaceBuilder,
    ) -> None:
        """Prepare a surface set over ``root``; creates no windows yet."""
        self._root = root
        self._config = config
        self._builder = builder
        self._surfaces: dict[str, _Surface] = {}

    def infos(self) -> tuple[SurfaceInfo, ...]:
        """Every current surface, in output order."""
        return tuple(
            surface.info
            for surface in sorted(self._surfaces.values(), key=lambda s: s.info.index)
        )

    def names(self) -> frozenset[str]:
        """The output names currently carrying a surface."""
        return frozenset(self._surfaces)

    def update_backdrop(self) -> None:
        """Size the root to the whole X screen and keep it black.

        The backdrop covers regions no live output claims -- including the dead
        column a modeless monitor leaves behind -- so nothing of the desktop
        shows through the gaps.
        """
        if not needs_backdrop_root(self._config):
            return
        width = self._root.winfo_screenwidth()
        height = self._root.winfo_screenheight()
        self._root.geometry(f"{width}x{height}+0+0")
        self._root.configure(bg=self._config.bg, cursor="arrow")

    def apply(self, scan: OutputScan) -> SurfaceDelta:
        """Bring the surface set in line with ``scan``.

        A failed scan must never reach this method: callers check ``scan.ok``
        first, because "we could not enumerate" is not evidence that anything
        should change.
        """
        live = scan.live
        wanted = {output.name: output for output in live}

        removed = tuple(name for name in sorted(self._surfaces) if name not in wanted)
        for name in removed:
            self._destroy(name)

        created: list[str] = []
        moved: list[str] = []
        for index, output in enumerate(live):
            rect = output.rect
            if rect is None:  # pragma: no cover - `live` guarantees a rect
                continue
            existing = self._surfaces.get(output.name)
            info = SurfaceInfo(
                output_name=output.name,
                rect=rect,
                index=index,
                is_primary=output.primary,
            )
            if existing is None:
                self._create(info)
                created.append(output.name)
            elif existing.info != info:
                self._reposition(existing, info)
                moved.append(output.name)

        return SurfaceDelta(
            created=tuple(created),
            moved=tuple(moved),
            removed=removed,
            unverified=self.verify(live_names=frozenset(wanted)),
        )

    def verify(self, *, live_names: frozenset[str] | None = None) -> tuple[str, ...]:
        """Return live outputs that are NOT currently showing a lock.

        This is the alarm for the original defect: an output the user can see,
        with no lock on it, means the escape UI is somewhere they cannot reach.
        """
        names = live_names if live_names is not None else self.names()
        return blind_outputs(self._surfaces, names)

    def enforce(self) -> tuple[str, ...]:
        """Re-assert every surface's placement and stacking.

        Only ever *adds* visibility: remaps what became unmapped, corrects
        drifted geometry, and raises. Nothing here can hide a surface.
        """
        return enforce_all(
            self._surfaces,
            overrideredirect=self._config.resolved_overrideredirect(),
        )

    def raise_all(self) -> None:
        """Lift every surface above whatever else is on screen."""
        for surface in self._surfaces.values():
            surface.window.lift()

    def focus_surface(self, index: int) -> SurfaceInfo | None:
        """Move keyboard focus to one surface, returning what got it."""
        for surface in self._surfaces.values():
            if surface.info.index == index:
                surface.window.focus_force()
                return surface.info
        return None

    def preferred_focus_index(self) -> int:
        """Index of the surface that should take initial focus.

        The live primary output if there is one, else the first surface.
        """
        for surface in self._surfaces.values():
            if surface.info.is_primary:
                return surface.info.index
        return 0

    def _create(self, info: SurfaceInfo) -> None:
        """Create one surface window and let the app build its UI inside."""
        window = tk.Toplevel(self._root)
        # Order matters and is not negotiable: a window must be withdrawn while
        # override-redirect is set, or the geometry below is ignored.
        window.withdraw()
        if self._config.resolved_overrideredirect():
            window.overrideredirect(boolean=True)
        window.configure(bg=self._config.bg, cursor="arrow")
        set_geometry(window, info.rect)
        if not self._config.resolved_overrideredirect():
            window.attributes("-topmost", _TOPMOST_ON)
        window.deiconify()
        window.lift()

        surface = _Surface(info=info, window=window)
        self._surfaces[info.output_name] = surface
        self._builder.build_surface(window, info)
        surface.built = True
        _logger.info(
            "lock surface up on %s at %s", info.output_name, info.rect.geometry()
        )

    def _reposition(self, surface: _Surface, info: SurfaceInfo) -> None:
        """Move an existing surface to a new rectangle.

        Deliberately a move, never a destroy-and-recreate: a layout change must
        not discard half-typed input.
        """
        surface.info = info
        set_geometry(surface.window, info.rect)
        surface.window.lift()
        _logger.info(
            "lock surface on %s moved to %s", info.output_name, info.rect.geometry()
        )

    def _destroy(self, name: str) -> None:
        """Tear down the surface for an output that is no longer live."""
        surface = self._surfaces.pop(name)
        self._builder.teardown_surface(surface.info)
        surface.window.destroy()
        _logger.info("lock surface on %s removed; that output went dark", name)

    def destroy_all(self) -> None:
        """Tear down every surface. Used only when the whole lock is closing."""
        for name in list(self._surfaces):
            self._destroy(name)
