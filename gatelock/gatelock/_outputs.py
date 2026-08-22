"""Enumerate X11 outputs and tell live ones apart from dark ones.

The distinction this module exists to make is ``connected`` versus **live**.
On 2026-07-25 a monitor came up ``connected``, with a valid EDID, and no
mode/CRTC -- physically dark, while X still reserved its slice of the root
window. A lock window sized from ``winfo_screenwidth()`` therefore spanned a
region the user could not see, and the escape UI was rendered into the dark.

So: an output is **live** only when it is connected *and* has a mode. Anything
else is a region no human can look at.

Two backends compute the same predicate:

* **RandR** via ``python-xlib`` -- authoritative. ``crtc == 0`` or ``mode == 0``
  *is* "connected but modeless".
* **``xrandr --query``** text -- a re-derivation of the same predicate for
  systems without ``python-xlib``.

``python-xlib`` is an optional dependency, so its import lives inside a
function rather than at module scope. That is deliberate and load-bearing: a
module-scope ``try/except ImportError`` is resolved at import time, which makes
the ``except`` arm permanently unreachable for branch coverage -- and this is
precisely the degradation path that must stay tested.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk

from gatelock._output_types import Output, OutputRect, OutputScan
from gatelock._randr import RandrBackend
from gatelock._xrandr import parse_xrandr_query, scan_xrandr

# Re-exported after the 250-line split, so `from gatelock._outputs import
# Output` -- which the tests and sibling modules do -- keeps resolving.
__all__ = [
    "Output",
    "OutputEnumerator",
    "OutputRect",
    "OutputScan",
    "RandrBackend",
    "enumerate_outputs",
    "parse_xrandr_query",
    "scan_xrandr",
    "tk_fallback_outputs",
]

_logger = logging.getLogger(__name__)


# Output lines start at column 0; mode lines are indented four spaces. That
# anchor is the whole robustness story -- without it, the mode line
# "   2560x1440  59.95*+" parses as a geometry and every modeless output
# silently looks live.
_OUTPUT_LINE = re.compile(
    r"^(?P<name>\S+)\s+(?P<state>connected|disconnected)\b(?P<rest>.*)$",
    re.MULTILINE,
)

"""Which backend produced a scan. Reported so logs can explain a degradation."""


def tk_fallback_outputs(root: tk.Misc) -> tuple[Output, ...]:
    """Synthesise one output covering the whole X screen.

    This is v0.1.1's behaviour, kept as a floor. It cannot tell a dark region
    from a live one, so it is strictly a last resort -- but a lock covering the
    full bounding box beats a lock covering nothing.
    """
    width = int(root.winfo_screenwidth())
    height = int(root.winfo_screenheight())
    return (
        Output(
            name="tk-screen",
            connected=True,
            rect=OutputRect(x=0, y=0, width=width, height=height),
        ),
    )


class OutputEnumerator:
    """Runs the backend ladder: RandR, then xrandr, then Tk, then nothing."""

    def __init__(
        self,
        root: tk.Misc | None = None,
        *,
        backend: RandrBackend | None = None,
    ) -> None:
        """Build an enumerator, opening a RandR connection when possible.

        Args:
            root: A Tk widget used only for the last-resort full-screen
                fallback. Without it, that rung is skipped.
            backend: A pre-opened RandR backend. Defaults to opening one.
        """
        self._root = root
        self._backend = backend if backend is not None else RandrBackend.create()

    @property
    def backend(self) -> RandrBackend | None:
        """The RandR backend, or None when python-xlib is unavailable."""
        return self._backend

    def close(self) -> None:
        """Release the RandR connection, if any."""
        if self._backend is not None:
            self._backend.close()
            self._backend = None

    def scan(self) -> OutputScan:
        """Enumerate outputs, degrading through the backend ladder."""
        if self._backend is not None:
            outputs = self._backend.scan()
            if outputs is not None:
                return OutputScan(outputs=outputs, source="randr", ok=True)
        outputs = scan_xrandr()
        if outputs is not None:
            return OutputScan(outputs=outputs, source="xrandr", ok=True)
        if self._root is not None:
            return OutputScan(
                outputs=tk_fallback_outputs(self._root), source="tk", ok=True
            )
        _logger.error(
            "every output-enumeration backend failed; reporting a failed scan "
            "so callers leave the lock exactly as it is"
        )
        return OutputScan(outputs=(), source="none", ok=False)


def enumerate_outputs(root: tk.Misc | None = None) -> OutputScan:
    """Enumerate outputs once, using a throwaway connection.

    Convenience for one-shot callers (CLI probes, tests). Long-lived callers
    should hold an :class:`OutputEnumerator` so the X connection is reused.
    """
    enumerator = OutputEnumerator(root)
    try:
        return enumerator.scan()
    finally:
        enumerator.close()
