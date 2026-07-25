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

from dataclasses import dataclass
import logging
import re
import shutil
import subprocess
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence
    import tkinter as tk

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

_XRANDR_TIMEOUT_S = 5.0

# RandR's `connection` field: 0 is RR_Connected. Hard-coded rather than
# imported so the constant is available without python-xlib installed.
_RR_CONNECTED = 0

# Output lines start at column 0; mode lines are indented four spaces. That
# anchor is the whole robustness story -- without it, the mode line
# "   2560x1440  59.95*+" parses as a geometry and every modeless output
# silently looks live.
_OUTPUT_LINE = re.compile(
    r"^(?P<name>\S+)\s+(?P<state>connected|disconnected)\b(?P<rest>.*)$",
    re.MULTILINE,
)
_GEOMETRY = re.compile(r"(?P<w>\d+)x(?P<h>\d+)\+(?P<x>-?\d+)\+(?P<y>-?\d+)")

OutputSource = Literal["randr", "xrandr", "tk", "none"]
"""Which backend produced a scan. Reported so logs can explain a degradation."""


@dataclass(frozen=True)
class OutputRect:
    """A rectangle in root-window coordinates."""

    x: int
    y: int
    width: int
    height: int

    def geometry(self) -> str:
        """Return the Tk geometry string for this rectangle."""
        return f"{self.width}x{self.height}+{self.x}+{self.y}"


@dataclass(frozen=True)
class Output:
    """A single X output and whether anything can actually be seen on it."""

    name: str
    connected: bool
    rect: OutputRect | None
    primary: bool = False

    @property
    def live(self) -> bool:
        """Whether this output is connected *and* has a mode."""
        return self.connected and self.rect is not None


@dataclass(frozen=True)
class OutputScan:
    """The result of one enumeration attempt.

    ``ok`` records whether enumeration itself succeeded, which is a different
    question from whether any output is live. Callers must not conflate them:
    a failed scan means "no information, change nothing", while a successful
    scan with zero live outputs means "the screens really are dark".
    """

    outputs: tuple[Output, ...]
    source: OutputSource
    ok: bool

    @property
    def live(self) -> tuple[Output, ...]:
        """The subset of outputs that are connected and have a mode."""
        return tuple(output for output in self.outputs if output.live)


def _parse_rect(head: str) -> OutputRect | None:
    """Parse a geometry token out of an xrandr output line's head segment."""
    match = _GEOMETRY.search(head)
    if match is None:
        return None
    width = int(match.group("w"))
    height = int(match.group("h"))
    if width <= 0 or height <= 0:
        return None
    return OutputRect(
        x=int(match.group("x")),
        y=int(match.group("y")),
        width=width,
        height=height,
    )


def parse_xrandr_query(text: str) -> tuple[Output, ...]:
    """Parse ``xrandr --query`` output into outputs.

    Args:
        text: Raw stdout from ``xrandr --query``.

    Returns:
        One :class:`Output` per output line, in the order xrandr listed them.
    """
    outputs: list[Output] = []
    for match in _OUTPUT_LINE.finditer(text):
        # Everything after the first "(" is rotation/reflection vocabulary and
        # panning noise -- never geometry. Slicing it off keeps the search
        # honest.
        head = match.group("rest").split("(", 1)[0]
        outputs.append(
            Output(
                name=match.group("name"),
                connected=match.group("state") == "connected",
                rect=_parse_rect(head),
                primary="primary" in head.split(),
            )
        )
    return tuple(outputs)


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


def scan_xrandr() -> tuple[Output, ...] | None:
    """Enumerate outputs by shelling out to ``xrandr --query``.

    Returns:
        The parsed outputs, or None if xrandr is missing, failed, timed out or
        produced nothing parseable.
    """
    binary = shutil.which("xrandr")
    if binary is None:
        _logger.warning("xrandr is not on PATH; cannot enumerate outputs")
        return None
    try:
        completed = subprocess.run(
            [binary, "--query"],
            capture_output=True,
            text=True,
            timeout=_XRANDR_TIMEOUT_S,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        _logger.warning("xrandr --query failed to run: %s", exc)
        return None
    if completed.returncode != 0:
        _logger.warning(
            "xrandr --query exited %d: %s",
            completed.returncode,
            completed.stderr.strip(),
        )
        return None
    outputs = parse_xrandr_query(completed.stdout)
    if not outputs:
        _logger.warning("xrandr --query produced no parseable output lines")
        return None
    return outputs


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
