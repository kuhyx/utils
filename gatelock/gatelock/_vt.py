"""VT-switch (Ctrl+Alt+Fn) disable/restore via setxkbmap.

Disabling VT switching is what stops a locked window from being bypassed by
dropping to a TTY. Best-effort: silently does nothing if setxkbmap isn't
installed, matching the behavior of every implementation this was ported from.
"""

from __future__ import annotations

import logging
import shutil
import subprocess

_logger = logging.getLogger(__name__)


def disable_vt_switching() -> bool:
    """Best-effort disable of Ctrl+Alt+Fn VT switching.

    Returns:
        True if setxkbmap was found and the disable command ran (the caller
        should later call :func:`restore_vt_switching`); False if setxkbmap
        is unavailable and VT switching could not be touched.
    """
    setxkbmap = shutil.which("setxkbmap")
    if setxkbmap is None:
        _logger.warning("setxkbmap not found; VT switching stays enabled")
        return False
    subprocess.run([setxkbmap, "-option", "srvrkeys:none"], check=False)
    return True


def restore_vt_switching() -> None:
    """Re-enable VT switching. Safe to call even if it was never disabled."""
    setxkbmap = shutil.which("setxkbmap")
    if setxkbmap is not None:
        subprocess.run([setxkbmap, "-option", ""], check=False)
