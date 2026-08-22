"""Tests for OutputEnumerator and the scan it returns.

Split from ``test_outputs.py`` (250-line cap). ``test_outputs_randr.py``
keeps the python-xlib backend itself; this covers the enumerator that drives
it and the OutputScan it produces.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from gatelock._randr import RandrBackend
from gatelock._outputs import (
    Output,
    OutputEnumerator,
    OutputRect,
    OutputScan,
    enumerate_outputs,
)

# Bound at import, so the autouse hermetic patch (which replaces these
# attributes) does not hide the real implementations from their own tests.
REAL_CREATE = RandrBackend.create.__func__

XRANDR_REAL = """\
Screen 0: minimum 8 x 8, current 6400 x 2160, maximum 32767 x 32767
HDMI-0 connected 2560x1440+3840+0 (normal left inverted right x axis) 597mm x 336mm
   2560x1440     59.95*+ 143.98   120.00
   1920x1080     60.00    59.94
DP-0 connected primary 3840x2160+0+0 (normal left inverted right x axis) 621mm x 341mm
   3840x2160     60.00*+ 144.00
DP-1 disconnected (normal left inverted right x axis y axis)
"""

XRANDR_INCIDENT = """\
Screen 0: minimum 8 x 8, current 6400 x 1440, maximum 32767 x 32767
HDMI-0 connected 2560x1440+3840+0 (normal left inverted right x axis) 600mm x 330mm
   2560x1440     59.95*+
DP-0 connected primary (normal left inverted right x axis y axis) 621mm x 341mm
   3840x2160     60.00 +
"""

XRANDR_ALL_DARK = """\
HDMI-0 connected (normal left inverted right x axis)
DP-0 connected primary (normal left inverted right x axis y axis)
"""

XRANDR_ROTATED = "DP-0 connected primary 1080x1920+0+0 left (normal left inverted)\n"
XRANDR_NEGATIVE = "DP-0 connected 1920x1080+-1920+0 (normal left inverted)\n"
XRANDR_ZERO_SIZE = "DP-0 connected 0x0+0+0 (normal left inverted)\n"
XRANDR_MODE_LINES_ONLY = "   2560x1440     59.95*+ 143.98\n   1920x1080  60.00\n"
XRANDR_GARBAGE = "segfault\n"


class TestOutputEnumerator:
    """Tests for the backend ladder."""

    def test_prefers_randr(self, mock_root: MagicMock) -> None:
        """When RandR answers, xrandr is never consulted."""
        backend = MagicMock()
        backend.scan.return_value = (
            Output("DP-0", connected=True, rect=OutputRect(0, 0, 1, 1)),
        )
        scan = OutputEnumerator(mock_root, backend=backend).scan()
        assert scan.source == "randr"
        assert scan.ok is True

    def test_falls_back_to_xrandr(self, mock_root: MagicMock) -> None:
        """A failed RandR scan drops to xrandr."""
        backend = MagicMock()
        backend.scan.return_value = None
        with patch(
            "gatelock._outputs.scan_xrandr",
            return_value=(Output("DP-0", connected=True, rect=OutputRect(0, 0, 1, 1)),),
        ):
            scan = OutputEnumerator(mock_root, backend=backend).scan()
        assert scan.source == "xrandr"

    def test_falls_back_to_tk(self, mock_root: MagicMock) -> None:
        """With neither backend, Tk's screen size is the floor."""
        with patch("gatelock._outputs.scan_xrandr", return_value=None):
            scan = OutputEnumerator(mock_root, backend=None).scan()
        assert scan.source == "tk"
        assert scan.live[0].rect == OutputRect(0, 0, 1920, 1080)

    def test_total_failure_is_not_ok(self) -> None:
        """With no root and no backend, the scan reports failure."""
        with patch("gatelock._outputs.scan_xrandr", return_value=None):
            scan = OutputEnumerator(None, backend=None).scan()
        assert scan.ok is False
        assert scan.source == "none"
        assert scan.live == ()

    def test_backend_property_and_close(self) -> None:
        """close() releases the backend once and is safe to repeat."""
        backend = MagicMock()
        enumerator = OutputEnumerator(None, backend=backend)
        assert enumerator.backend is backend
        enumerator.close()
        enumerator.close()
        backend.close.assert_called_once_with()

    def test_enumerate_outputs_helper(self, mock_root: MagicMock) -> None:
        """The one-shot helper works and cleans up after itself."""
        with patch("gatelock._outputs.scan_xrandr", return_value=None):
            scan = enumerate_outputs(mock_root)
        assert scan.source == "tk"


class TestOutputScan:
    """Tests for OutputScan's live filter."""

    def test_live_filters_dark_outputs(self) -> None:
        """Only connected-with-mode outputs are live."""
        scan = OutputScan(
            outputs=(
                Output("DP-0", connected=True, rect=None),
                Output("HDMI-0", connected=True, rect=OutputRect(0, 0, 1, 1)),
                Output("DP-1", connected=False, rect=None),
            ),
            source="randr",
            ok=True,
        )
        assert [o.name for o in scan.live] == ["HDMI-0"]
