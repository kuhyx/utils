"""The value types describing a lock surface and a change to the set of them.

Split from :mod:`gatelock._surfaces` for the 250-line cap. Data and one
Protocol, no behaviour, so an app can type against a surface without
importing the machinery that builds one.

Re-exported from :mod:`gatelock._surfaces`, so existing imports of these
names keep working.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import tkinter as tk

    from gatelock._outputs import OutputRect


@dataclass(frozen=True)
class SurfaceInfo:
    """Identifies one lock surface and the output it covers."""

    output_name: str
    rect: OutputRect
    index: int
    is_primary: bool


class SurfaceBuilder(Protocol):
    """What a consuming app must implement to paint its UI on each output."""

    def build_surface(self, parent: tk.Misc, surface: SurfaceInfo) -> None:
        """Build this app's widgets inside ``parent`` for one output."""

    def teardown_surface(self, surface: SurfaceInfo) -> None:
        """Forget any per-surface state; the window is about to be destroyed."""


@dataclass(frozen=True)
class SurfaceDelta:
    """What one :meth:`SurfaceSet.apply` changed."""

    created: tuple[str, ...] = ()
    moved: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    unverified: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        """Whether anything structural happened."""
        return bool(self.created or self.moved or self.removed)
