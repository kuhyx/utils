# Copyright (c) 2026 Krzysztof Rudnicki
"""Re-taking a lost global grab, once per recovery tick.

Split out of :mod:`gatelock._recovery` for the 250-line cap, and kept in its
``_recovery_*`` family on purpose: the static invariant test globs the family,
so this file is held to the same rule -- it may take the grab, never release it.
"""

from __future__ import annotations

import logging
import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gatelock._grabwatch import GrabWatch
    from gatelock._recovery_types import RecoveryCollaborators

_logger = logging.getLogger(__name__)


def reassert_grab(
    root: tk.Misc, parts: RecoveryCollaborators, watch: GrabWatch
) -> bool:
    """Re-take the global grab if we lost it. Never releases one.

    A failed attempt is reported with Tk's own message (once per distinct
    message: this runs every tick) and timed by the prompt-yield policy. A
    grab we hold ends any yield, and then the lock is lifted over whatever it
    had stepped aside for.

    Args:
        root: The Tk root that holds the grab.
        parts: The loop's collaborators.
        watch: Answers "is the grab ours?" and throttles the warning.

    Returns:
        True if the grab had to be re-taken.
    """
    if parts.config.resolved_grab() != "global":
        return False
    held = watch.holds_grab()
    reasserted = False
    if not held:
        try:
            parts.prompt_yield.check_grab()
            root.grab_set_global()
        except tk.TclError as exc:
            parts.prompt_yield.grab_blocked(str(exc))
            watch.warn_once(f"could not re-take the global grab ({exc})")
        else:
            _logger.warning("global grab had been lost; re-acquired it")
            reasserted = held = True
    if held and parts.prompt_yield.grab_held():
        parts.surfaces.raise_all()
    parts.on_grab_held(held=held)
    return reasserted
