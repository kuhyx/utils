# Copyright (c) 2026 Krzysztof Rudnicki
"""Where a lock surface sits, and putting it back when it drifts.

Split from :mod:`gatelock._surfaces`, which owns creating and destroying the
windows. This half owns the geometry questions -- is the window mapped, is it
still exactly on its output -- and the re-assertion pass that answers "no" by
correcting it.

Everything the recovery loop reaches here only ever *adds* visibility; that
asymmetry is what makes it monotonic. The one hider, :func:`set_visible`, is
reached only by :mod:`gatelock._stepback`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    import tkinter as tk

    from gatelock._config import LockConfig
    from gatelock._outputs import OutputRect
    from gatelock._surfaces import SurfaceInfo


@dataclass
class _Surface:
    """One Toplevel and the output it is pinned to."""

    info: SurfaceInfo
    window: tk.Toplevel
    built: bool = field(default=False)


def set_geometry(window: tk.Toplevel, rect: OutputRect) -> None:
    """Pin a window to an output's rectangle."""
    window.geometry(rect.geometry())


def is_mapped(surface: _Surface) -> bool:
    """Whether a surface's window is currently mapped."""
    return bool(surface.window.winfo_ismapped())


def geometry_matches(surface: _Surface) -> bool:
    """Whether a surface still sits exactly on its output."""
    rect = surface.info.rect
    window = surface.window
    return (
        window.winfo_rootx() == rect.x
        and window.winfo_rooty() == rect.y
        and window.winfo_width() == rect.width
        and window.winfo_height() == rect.height
    )


def enforce_one(
    surface: _Surface, *, overrideredirect: bool, lift: bool = True
) -> bool:
    """Re-assert one surface's placement and stacking.

    Args:
        surface: The surface to correct.
        overrideredirect: Whether the lock runs WM-unmanaged, in which case
            the flag is re-set -- it can be dropped across an unmap/map cycle,
            and a managed lock window would be moved by the WM.
        lift: Whether to raise the window. False only while a system prompt
            is being yielded to (:mod:`gatelock._prompts`); placement and
            mapping are corrected either way.

    Returns:
        True if anything needed correcting.
    """
    window = surface.window
    changed = False
    if not is_mapped(surface):
        window.deiconify()
        changed = True
    if not geometry_matches(surface):
        set_geometry(window, surface.info.rect)
        changed = True
    if overrideredirect:
        window.overrideredirect(boolean=True)
    if lift:
        window.lift()
    return changed


def set_visible(
    surfaces: Mapping[str, _Surface], *, visible: bool, overrideredirect: bool
) -> None:
    """Hide or show every surface. Only a stepping-back lock ever hides.

    Showing restores the creation order (override-redirect while still
    unmapped, geometry, then map and raise) rather than ``enforce_one``'s
    map-first order, so a surface cannot come back window-manager-managed.
    """
    for surface in surfaces.values():
        window = surface.window
        if not visible:
            window.withdraw()
            continue
        if overrideredirect:
            window.overrideredirect(boolean=True)
        set_geometry(window, surface.info.rect)
        window.deiconify()
        window.lift()


def blind_outputs(
    surfaces: Mapping[str, _Surface], names: frozenset[str]
) -> tuple[str, ...]:
    """Live outputs that are NOT currently showing a lock.

    This is the alarm for the original defect: an output the user can see,
    with no lock on it, means the escape UI is somewhere they cannot reach.

    Args:
        surfaces: The live surfaces, keyed by output name.
        names: The outputs that should be covered.

    Returns:
        The uncovered output names, sorted.
    """
    blind: list[str] = []
    for name in sorted(names):
        surface = surfaces.get(name)
        if surface is None or not is_mapped(surface):
            blind.append(name)
    return tuple(blind)


def enforce_all(
    surfaces: Mapping[str, _Surface], *, overrideredirect: bool, lift: bool = True
) -> tuple[str, ...]:
    """Re-assert every surface's placement and stacking.

    Args:
        surfaces: The live surfaces, keyed by output name.
        overrideredirect: Whether the lock runs WM-unmanaged.
        lift: Whether to raise the surfaces; see :func:`enforce_one`.

    Returns:
        The names of the outputs whose surfaces needed correcting, sorted.
    """
    corrected = [
        surface.info.output_name
        for surface in surfaces.values()
        if enforce_one(surface, overrideredirect=overrideredirect, lift=lift)
    ]
    return tuple(sorted(corrected))


def needs_backdrop_root(config: LockConfig) -> bool:
    """Whether the root must stay mapped as a backdrop and grab holder.

    Deliberately *not* simplified to "iff override-redirect".
    ``LockConfig(mode="soft", grab="global")`` is a reachable combination, and
    a global grab requires a viewable window -- X refuses to grab for a
    withdrawn one. Collapsing this predicate would make that config fail at
    runtime only.
    """
    return config.resolved_overrideredirect() or config.resolved_grab() != "none"
