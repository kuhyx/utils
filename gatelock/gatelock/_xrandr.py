"""Reading outputs by shelling out to `xrandr --query`.

Split from :mod:`gatelock._outputs`, which keeps the value types and the
enumerator that picks a source. This is the fallback path: slower than the
RandR backend in :mod:`gatelock._randr` and it cannot deliver change events,
but it needs no optional dependency, so it is what runs on a bare install.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess

from gatelock._output_types import Output, OutputRect

_logger = logging.getLogger(__name__)

_XRANDR_TIMEOUT_S = 5.0

# Output lines start at column 0; mode lines are indented four spaces. That
# anchor is the whole robustness story -- without it, the mode line
# "   2560x1440  59.95*+" parses as a geometry and every modeless output
# silently looks live.
_OUTPUT_LINE = re.compile(
    r"^(?P<name>\S+)\s+(?P<state>connected|disconnected)\b(?P<rest>.*)$",
    re.MULTILINE,
)
_GEOMETRY = re.compile(r"(?P<w>\d+)x(?P<h>\d+)\+(?P<x>-?\d+)\+(?P<y>-?\d+)")

_GEOMETRY = re.compile(r"(?P<w>\d+)x(?P<h>\d+)\+(?P<x>-?\d+)\+(?P<y>-?\d+)")


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
