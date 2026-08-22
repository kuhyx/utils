"""The python-xlib RandR backend: instant output-change events.

Split from :mod:`gatelock._outputs`, which keeps the value types and the
xrandr-subprocess path. python-xlib is an optional dependency -- without it
the lock still detects output changes, just by polling -- so everything that
touches it lives here, behind :meth:`RandrBackend.create`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

from gatelock._output_types import Output, OutputRect

if TYPE_CHECKING:
    from collections.abc import Sequence

    # python-xlib ships no type stubs. Rather than typing its objects as ``Any``
    # (or reaching for a suppression comment, which this repo bans), these
    # protocols spell out the exact surface gatelock depends on. If a future
    # python-xlib renames one of these, the type checker says so.
    class _ScreenResources(Protocol):
        config_timestamp: int
        outputs: Sequence[int]

    class _OutputInfo(Protocol):
        name: object
        connection: int
        crtc: int

    class _CrtcInfo(Protocol):
        mode: int
        x: int
        y: int
        width: int
        height: int

    class _PrimaryReply(Protocol):
        output: int

    class _XRoot(Protocol):
        def xrandr_get_screen_resources(self) -> _ScreenResources: ...

        def xrandr_get_output_primary(self) -> _PrimaryReply: ...

    class _XScreen(Protocol):
        root: _XRoot

    class _XDisplay(Protocol):
        def screen(self) -> _XScreen: ...

        def xrandr_get_output_info(
            self, output: int, timestamp: int
        ) -> _OutputInfo: ...

        def xrandr_get_crtc_info(self, crtc: int, timestamp: int) -> _CrtcInfo: ...

        def close(self) -> None: ...

_logger = logging.getLogger(__name__)

# RandR's `connection` field: 0 is RR_Connected. Hard-coded rather than
# imported so the constant is available without python-xlib installed.
_RR_CONNECTED = 0

def _decode_name(raw: object) -> str:
    """Normalise a RandR output name, which may arrive as bytes."""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


class RandrBackend:
    """A persistent X connection used to enumerate outputs via RandR.

    Held open across scans -- the recovery loop scans every second, and opening
    a fresh X connection each time would be pure waste.
    """

    def __init__(self, display: _XDisplay) -> None:
        """Wrap an already-opened ``Xlib.display.Display``."""
        self._display = display

    @classmethod
    def create(cls) -> RandrBackend | None:
        """Open an X connection for RandR queries, or None if unavailable."""
        try:
            from Xlib import display as xdisplay
        except ImportError:
            _logger.debug(
                "python-xlib is not installed; RandR events and RandR "
                "enumeration are unavailable, falling back to xrandr"
            )
            return None
        try:
            return cls(xdisplay.Display())
        except (OSError, ValueError) as exc:
            _logger.warning("could not open an X display for RandR: %s", exc)
            return None

    def close(self) -> None:
        """Close the underlying X connection, ignoring teardown errors."""
        try:
            self._display.close()
        except (OSError, ValueError, AttributeError) as exc:
            _logger.debug("ignoring error while closing RandR display: %s", exc)

    def scan(self) -> tuple[Output, ...] | None:
        """Enumerate outputs, or None if the RandR query failed."""
        try:
            return self._scan()
        except (OSError, ValueError, KeyError, AttributeError, TypeError) as exc:
            _logger.warning("RandR enumeration failed (%s); falling back", exc)
            return None

    def _scan(self) -> tuple[Output, ...]:
        """Enumerate outputs via RandR. Raises on any protocol problem."""
        root = self._display.screen().root
        resources = root.xrandr_get_screen_resources()
        timestamp = resources.config_timestamp
        primary_id = self._primary_output_id(root)

        outputs: list[Output] = []
        for output_id in resources.outputs:
            info = self._display.xrandr_get_output_info(output_id, timestamp)
            outputs.append(
                Output(
                    name=_decode_name(info.name),
                    connected=info.connection == _RR_CONNECTED,
                    rect=self._crtc_rect(info.crtc, timestamp),
                    primary=output_id == primary_id,
                )
            )
        return tuple(outputs)

    def _primary_output_id(self, root: _XRoot) -> int | None:
        """Return the primary output's id, or None when RandR won't say."""
        try:
            return root.xrandr_get_output_primary().output
        except (OSError, ValueError, KeyError, AttributeError, TypeError):
            return None

    def _crtc_rect(self, crtc: int, timestamp: int) -> OutputRect | None:
        """Return the CRTC's rectangle, or None when there is no mode.

        ``crtc == 0`` means no CRTC is assigned and ``mode == 0`` means a CRTC
        exists without a mode. Either one is the dark-monitor case.
        """
        if not crtc:
            return None
        info = self._display.xrandr_get_crtc_info(crtc, timestamp)
        if not info.mode or info.width <= 0 or info.height <= 0:
            return None
        return OutputRect(x=info.x, y=info.y, width=info.width, height=info.height)


