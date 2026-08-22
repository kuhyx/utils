"""Tests for the python-xlib RandR backend and the enumerator over it.

Split from ``test_outputs.py`` (250-line cap), which keeps rect geometry,
the live predicate, and xrandr-query parsing.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from gatelock._outputs import (
    OutputRect,
    RandrBackend,
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
