"""Tests for output enumeration and the live-vs-dark predicate.

The regression that matters most is :data:`XRANDR_INCIDENT`: on 2026-07-25 an
output reported ``connected`` with a valid EDID and no geometry, and every
consumer treated it as usable screen real estate.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from gatelock._outputs import (
    Output,
    OutputEnumerator,
    OutputRect,
    OutputScan,
    RandrBackend,
    _decode_name,
    enumerate_outputs,
    parse_xrandr_query,
)
from gatelock._outputs import scan_xrandr as real_scan_xrandr

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


class TestOutputRect:
    """Tests for OutputRect."""

    def test_geometry_string(self) -> None:
        """A rect renders as Tk's WxH+X+Y form."""
        assert OutputRect(3840, 0, 2560, 1440).geometry() == "2560x1440+3840+0"

    def test_geometry_with_negative_offset(self) -> None:
        """Negative offsets survive the round trip."""
        assert OutputRect(-1920, 0, 1920, 1080).geometry() == "1920x1080+-1920+0"


class TestLivePredicate:
    """Connected is not the same as live."""

    def test_connected_with_mode_is_live(self) -> None:
        """A connected output with a rect is live."""
        assert Output("DP-0", connected=True, rect=OutputRect(0, 0, 1, 1)).live

    def test_connected_without_mode_is_not_live(self) -> None:
        """THE incident: connected, EDID present, no mode -> not live."""
        assert not Output("DP-0", connected=True, rect=None).live

    def test_disconnected_is_not_live(self) -> None:
        """A disconnected output is not live even if a rect lingers."""
        assert not Output("DP-1", connected=False, rect=OutputRect(0, 0, 1, 1)).live


class TestParseXrandrQuery:
    """Tests for the xrandr text parser."""

    def test_real_layout(self) -> None:
        """Both live outputs are found with exact geometry, plus primary."""
        outputs = parse_xrandr_query(XRANDR_REAL)
        assert [o.name for o in outputs] == ["HDMI-0", "DP-0", "DP-1"]
        by_name = {o.name: o for o in outputs}
        assert by_name["DP-0"].rect == OutputRect(0, 0, 3840, 2160)
        assert by_name["DP-0"].primary is True
        assert by_name["HDMI-0"].rect == OutputRect(3840, 0, 2560, 1440)
        assert by_name["HDMI-0"].primary is False
        assert by_name["DP-1"].connected is False

    def test_the_incident(self) -> None:
        """DP-0 connected-but-modeless is parsed as not live."""
        outputs = parse_xrandr_query(XRANDR_INCIDENT)
        by_name = {o.name: o for o in outputs}
        assert by_name["DP-0"].connected is True
        assert by_name["DP-0"].rect is None
        assert by_name["DP-0"].live is False
        assert [o.name for o in outputs if o.live] == ["HDMI-0"]

    def test_all_dark(self) -> None:
        """Every output connected and modeless yields zero live."""
        assert not [o for o in parse_xrandr_query(XRANDR_ALL_DARK) if o.live]

    def test_mode_lines_are_never_geometry(self) -> None:
        """Indented mode lines must not be read as output lines."""
        assert parse_xrandr_query(XRANDR_MODE_LINES_ONLY) == ()

    def test_rotated_reports_post_rotation_size(self) -> None:
        """xrandr already reports rotated geometry; no special handling."""
        (output,) = parse_xrandr_query(XRANDR_ROTATED)
        assert output.rect == OutputRect(0, 0, 1080, 1920)

    def test_negative_offset(self) -> None:
        """A monitor placed left of origin parses correctly."""
        (output,) = parse_xrandr_query(XRANDR_NEGATIVE)
        assert output.rect == OutputRect(-1920, 0, 1920, 1080)

    def test_zero_size_rejected(self) -> None:
        """A 0x0 geometry is not a usable screen."""
        (output,) = parse_xrandr_query(XRANDR_ZERO_SIZE)
        assert output.rect is None

    def test_garbage_and_empty(self) -> None:
        """Unparsable input yields no outputs rather than raising."""
        assert parse_xrandr_query(XRANDR_GARBAGE) == ()
        assert parse_xrandr_query("") == ()


class TestScanXrandr:
    """Tests for the xrandr subprocess wrapper, including every failure mode."""

    def _run(self, **kwargs: object) -> tuple[Output, ...] | None:
        with (
            patch("gatelock._outputs.shutil.which", return_value="/usr/bin/xrandr"),
            patch("gatelock._outputs.subprocess.run", **kwargs),
        ):
            return real_scan_xrandr()

    def test_success(self) -> None:
        """A clean run parses stdout."""
        completed = MagicMock(returncode=0, stdout=XRANDR_REAL, stderr="")
        assert self._run(return_value=completed) is not None

    def test_missing_binary(self) -> None:
        """xrandr not on PATH degrades rather than raising."""
        with patch("gatelock._outputs.shutil.which", return_value=None):
            assert real_scan_xrandr() is None

    def test_nonzero_exit(self) -> None:
        """A non-zero exit is a failed scan."""
        completed = MagicMock(returncode=1, stdout="", stderr="no display")
        assert self._run(return_value=completed) is None

    def test_timeout(self) -> None:
        """A hung xrandr is a failed scan, not a hung locker."""
        exc = subprocess.TimeoutExpired(cmd="xrandr", timeout=5)
        assert self._run(side_effect=exc) is None

    def test_oserror(self) -> None:
        """An OSError launching xrandr is a failed scan."""
        assert self._run(side_effect=OSError("boom")) is None

    def test_unparseable_output(self) -> None:
        """Exit 0 with nothing parseable is still a failed scan."""
        completed = MagicMock(returncode=0, stdout=XRANDR_GARBAGE, stderr="")
        assert self._run(return_value=completed) is None


class TestDecodeName:
    """RandR output names may arrive as bytes."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [(b"DP-0", "DP-0"), ("HDMI-0", "HDMI-0"), (b"\xff", "�")],
    )
    def test_decode(self, raw: object, expected: str) -> None:
        """Bytes are decoded, str passes through, bad bytes are replaced."""
        assert _decode_name(raw) == expected


def _reply(**fields: object) -> MagicMock:
    """An Xlib reply exposing its fields as attributes, as python-xlib does."""
    reply = MagicMock()
    for key, value in fields.items():
        setattr(reply, key, value)
    return reply


def _randr_display(*, outputs: dict[int, dict[str, object]]) -> MagicMock:
    """Build a fake Xlib display exposing ``outputs``."""
    display = MagicMock()
    root = MagicMock()
    root.xrandr_get_screen_resources.return_value = _reply(
        config_timestamp=1, outputs=list(outputs)
    )
    root.xrandr_get_output_primary.return_value = _reply(output=1)
    display.screen.return_value.root = root

    def output_info(output_id: int, _ts: int) -> MagicMock:
        return _reply(**outputs[output_id]["info"])

    def crtc_info(crtc: int, _ts: int) -> MagicMock:
        return _reply(**outputs[crtc]["crtc"])

    display.xrandr_get_output_info.side_effect = output_info
    display.xrandr_get_crtc_info.side_effect = crtc_info
    return display


class TestRandrBackend:
    """Tests for the RandR backend."""

    def test_scan_maps_crtc_to_rect(self) -> None:
        """A connected output with a CRTC and mode becomes a live rect."""
        display = _randr_display(
            outputs={
                1: {
                    "info": {"name": "DP-0", "connection": 0, "crtc": 1},
                    "crtc": {"mode": 55, "x": 0, "y": 0, "width": 3840, "height": 2160},
                }
            }
        )
        (output,) = RandrBackend(display).scan() or ()
        assert output.name == "DP-0"
        assert output.live is True
        assert output.primary is True
        assert output.rect == OutputRect(0, 0, 3840, 2160)

    def test_no_crtc_is_not_live(self) -> None:
        """crtc == 0 is the dark-monitor case."""
        display = _randr_display(
            outputs={1: {"info": {"name": "DP-0", "connection": 0, "crtc": 0}}}
        )
        (output,) = RandrBackend(display).scan() or ()
        assert output.connected is True
        assert output.rect is None

    def test_crtc_without_mode_is_not_live(self) -> None:
        """A CRTC exists but carries no mode: still dark."""
        display = _randr_display(
            outputs={
                1: {
                    "info": {"name": "DP-0", "connection": 0, "crtc": 1},
                    "crtc": {"mode": 0, "x": 0, "y": 0, "width": 0, "height": 0},
                }
            }
        )
        (output,) = RandrBackend(display).scan() or ()
        assert output.rect is None

    def test_zero_size_crtc_is_not_live(self) -> None:
        """A mode with no pixels is not a screen."""
        display = _randr_display(
            outputs={
                1: {
                    "info": {"name": "DP-0", "connection": 0, "crtc": 1},
                    "crtc": {"mode": 55, "x": 0, "y": 0, "width": 0, "height": 1080},
                }
            }
        )
        (output,) = RandrBackend(display).scan() or ()
        assert output.rect is None

    def test_disconnected(self) -> None:
        """connection != 0 means disconnected."""
        display = _randr_display(
            outputs={1: {"info": {"name": "DP-1", "connection": 1, "crtc": 0}}}
        )
        (output,) = RandrBackend(display).scan() or ()
        assert output.connected is False

    def test_scan_failure_returns_none(self) -> None:
        """A protocol error degrades to None instead of raising."""
        display = MagicMock()
        display.screen.side_effect = OSError("connection reset")
        assert RandrBackend(display).scan() is None

    def test_primary_query_failure_is_tolerated(self) -> None:
        """RandR refusing to name a primary is not fatal."""
        display = _randr_display(
            outputs={1: {"info": {"name": "DP-0", "connection": 0, "crtc": 0}}}
        )
        root = display.screen.return_value.root
        root.xrandr_get_output_primary.side_effect = OSError("nope")
        (output,) = RandrBackend(display).scan() or ()
        assert output.primary is False

    def test_close_swallows_errors(self) -> None:
        """Teardown never raises."""
        display = MagicMock()
        display.close.side_effect = OSError("already gone")
        RandrBackend(display).close()

    def test_close_normal(self) -> None:
        """A clean close closes the display."""
        display = MagicMock()
        RandrBackend(display).close()
        display.close.assert_called_once_with()


class TestCreateWithoutXlib:
    """RandrBackend.create's degradation path, exercised without the patch."""

    def test_import_error_returns_none(self) -> None:
        """A missing python-xlib degrades to None, never an exception.

        This is the branch the function-scope import exists to keep reachable.
        """
        with patch.dict("sys.modules", {"Xlib": None}):
            assert REAL_CREATE(RandrBackend) is None

    def test_display_error_returns_none(self) -> None:
        """A display that refuses to open returns None."""
        fake_display = MagicMock()
        fake_display.Display.side_effect = OSError("cannot connect")
        # `from Xlib import display` reads the attribute off the parent
        # module, so wiring sys.modules alone is not enough.
        fake_xlib = MagicMock(display=fake_display)
        with patch.dict(
            "sys.modules",
            {"Xlib": fake_xlib, "Xlib.display": fake_display},
        ):
            assert REAL_CREATE(RandrBackend) is None

    def test_success_returns_backend(self) -> None:
        """A working python-xlib yields a usable backend."""
        fake_display = MagicMock()
        fake_xlib = MagicMock(display=fake_display)
        with patch.dict(
            "sys.modules",
            {"Xlib": fake_xlib, "Xlib.display": fake_display},
        ):
            backend = REAL_CREATE(RandrBackend)
        assert isinstance(backend, RandrBackend)


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
