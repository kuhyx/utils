"""Bringing the lock up: VT-disable, backdrop, surfaces, and the input grab.

Split out of :mod:`gatelock._window`, which keeps the object's construction
and its teardown. Everything here runs once, in order, on the way *up* --
:func:`setup` makes the lock visible and :func:`grab_input` makes it
exclusive.

Arming order matters and is deliberate: **arm first, render second.** The grab
and the VT-disable happen regardless of how many outputs are live, and the
surfaces are then built for whatever the user can actually see -- possibly
nothing. Zero live outputs means "lock without showing", never "decline to
lock". The inverse of that rule is what left the machine unlocked on
2026-07-25.

These are free functions over an explicit :class:`ArmingCollaborators` bundle
rather than methods, mirroring :class:`gatelock._recovery.RecoveryCollaborators`.
Nothing here reaches back into the window, so the arming sequence can be read
-- and tested -- without one.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
import logging
import tkinter as tk
from typing import TYPE_CHECKING

from gatelock._surfaces import needs_backdrop_root
from gatelock._vt import disable_vt_switching

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock._config import LockConfig
    from gatelock._detect import OutputChangeDetector
    from gatelock._outputs import OutputEnumerator
    from gatelock._recovery import RecoveryLoop
    from gatelock._surfaces import SurfaceSet

_logger = logging.getLogger(__name__)

# Tk's attributes() takes the value positionally, so a bare `True` here trips
# the boolean-positional lint. Naming it satisfies both that rule and the type
# stubs, which have no keyword overload.
_TOPMOST_ON = True

# Default retry interval for a "global" grab that initially fails (e.g. a
# fullscreen game holds it). Used whenever grab_retry_ms is left unset.
_DEFAULT_GRAB_RETRY_MS = 200


@dataclass(frozen=True)
class ArmingCollaborators:
    """Everything the arming sequence needs from its owning window.

    Attributes:
        config: Declarative lock behavior for this instance.
        surfaces: The per-output surface set to build into.
        enumerator: Source of the live-output scan.
        detector: Output-change watcher, started once the grab is taken.
        recovery: Re-assertion loop, started alongside the detector.
        notify_focus_ready: Called once the lock is mapped and grabbed.
        log_grab_blocked: Called with the attempt count when a global grab is
            still blocked, to name the holder and stand a weaker one down.
    """

    config: LockConfig
    surfaces: SurfaceSet
    enumerator: OutputEnumerator
    detector: OutputChangeDetector
    recovery: RecoveryLoop
    notify_focus_ready: Callable[[], None]
    log_grab_blocked: Callable[[int], None]


def setup(root: tk.Tk, collab: ArmingCollaborators) -> bool:
    """Configure the backdrop and build a surface on every live output.

    Disables VT switching first: strengthening the lock must not wait on
    being able to draw anything. If no output is live, no surface is built
    and the lock stays armed and invisible until one appears.

    Args:
        root: The Tk root acting as backdrop and grab holder.
        collab: The window's arming collaborators.

    Returns:
        Whether VT switching was disabled, for the caller to remember so the
        matching restore happens exactly once on the way back down.
    """
    vt_disabled = False
    if collab.config.resolved_disable_vt():
        vt_disabled = disable_vt_switching()

    if needs_backdrop_root(collab.config):
        # The root is a plain black backdrop spanning the whole X screen,
        # including any region a modeless output left behind. It holds the
        # grab (X will not grab for a window that is not viewable) and
        # never carries widgets.
        root.overrideredirect(boolean=collab.config.resolved_overrideredirect())
        collab.surfaces.update_backdrop()
    else:
        root.attributes("-topmost", _TOPMOST_ON)

    scan = collab.enumerator.scan()
    delta = collab.surfaces.apply(scan)
    if not scan.live:
        _logger.warning(
            "no live outputs at startup (source=%s); arming the lock with "
            "nothing displayed -- it will appear as soon as a monitor "
            "comes back",
            scan.source,
        )
    else:
        _logger.info(
            "lock armed on %d output(s): %s",
            len(scan.live),
            ", ".join(output.name for output in scan.live),
        )
    if delta.unverified:
        _logger.error(
            "outputs live but not covered at startup: %s",
            ", ".join(delta.unverified),
        )
    return vt_disabled


def grab_input(root: tk.Tk, collab: ArmingCollaborators) -> None:
    """Take the configured grab, then start watching for output changes.

    Args:
        root: The Tk root that holds the grab.
        collab: The window's arming collaborators.
    """
    root.update_idletasks()
    root.focus_force()
    grab = collab.config.resolved_grab()
    if grab == "global":
        acquire_global_grab(root, collab, attempt=1)
    elif grab == "local":
        with contextlib.suppress(tk.TclError):
            root.grab_set()
    collab.detector.start()
    collab.recovery.start()
    root.after(100, collab.notify_focus_ready)


def acquire_global_grab(
    root: tk.Tk, collab: ArmingCollaborators, *, attempt: int
) -> None:
    """Acquire the global input grab, retrying per ``grab_retry_ms``.

    Args:
        root: The Tk root that holds the grab.
        collab: The window's arming collaborators.
        attempt: 1-based attempt counter, used only to throttle the log.
    """
    retry_ms = collab.config.grab_retry_ms
    try:
        root.grab_set_global()
    except tk.TclError:
        if retry_ms == 0:
            _logger.warning("Global grab failed, falling back to local grab")
            with contextlib.suppress(tk.TclError):
                root.grab_set()
            return
        effective_retry_ms = retry_ms or _DEFAULT_GRAB_RETRY_MS
        if not attempt % collab.config.grab_log_every:
            collab.log_grab_blocked(attempt)
        root.after(
            effective_retry_ms,
            lambda: acquire_global_grab(root, collab, attempt=attempt + 1),
        )
        return
    with contextlib.suppress(tk.TclError):
        root.focus_force()
        collab.notify_focus_ready()
