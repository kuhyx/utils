"""Tests for focus handling, the backdrop, teardown and the text mirror.

Split from ``test_surfaces.py`` to hold the shared 250-line cap.
"""


from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gatelock._outputs import Output, OutputRect, OutputScan
from gatelock._surfaces import (
    SurfaceInfo,
    SurfaceSet,
    TextMirror,
    mirror_text_widgets,
)
from gatelock._window import LockConfig

DP0 = Output("DP-0", connected=True, rect=OutputRect(0, 0, 3840, 2160), primary=True)
HDMI = Output("HDMI-0", connected=True, rect=OutputRect(3840, 0, 2560, 1440))
DP0_DARK = Output("DP-0", connected=True, rect=None, primary=True)
DP0_MOVED = Output(
    "DP-0", connected=True, rect=OutputRect(0, 0, 1920, 1080), primary=True
)


def scan(*outputs: Output) -> OutputScan:
    """Build a successful scan over ``outputs``."""
    return OutputScan(outputs=outputs, source="randr", ok=True)


@pytest.fixture
def surfaces(mock_root: MagicMock) -> SurfaceSet:
    """A hard-mode surface set over a mock root."""
    return SurfaceSet(mock_root, LockConfig(mode="hard"), MagicMock())


class TestFocus:
    """Which surface takes the keyboard."""

    def test_focus_surface_by_index(self, surfaces: SurfaceSet) -> None:
        """Focusing an index returns that surface's info."""
        surfaces.apply(scan(DP0, HDMI))
        info = surfaces.focus_surface(1)
        assert info is not None
        assert info.output_name == "HDMI-0"

    def test_focus_unknown_index(self, surfaces: SurfaceSet) -> None:
        """An index with no surface returns None."""
        surfaces.apply(scan(DP0))
        assert surfaces.focus_surface(9) is None

    def test_preferred_index_is_the_primary(self, surfaces: SurfaceSet) -> None:
        """The live primary output takes initial focus."""
        surfaces.apply(scan(HDMI, DP0))
        assert surfaces.preferred_focus_index() == 1

    def test_preferred_index_defaults_to_first(self, surfaces: SurfaceSet) -> None:
        """With no primary marked, the first surface wins."""
        surfaces.apply(scan(HDMI))
        assert surfaces.preferred_focus_index() == 0


class TestBackdropAndTeardown:
    """The root backdrop and full teardown."""

    def test_backdrop_covers_the_whole_screen(
        self, surfaces: SurfaceSet, mock_root: MagicMock
    ) -> None:
        """The backdrop spans the X screen, covering dead columns."""
        surfaces.update_backdrop()
        mock_root.geometry.assert_called_once_with("1920x1080+0+0")

    def test_soft_mode_has_no_backdrop(self, mock_root: MagicMock) -> None:
        """Without a grab or overrideredirect there is nothing to back."""
        SurfaceSet(mock_root, LockConfig(mode="soft"), MagicMock()).update_backdrop()
        mock_root.geometry.assert_not_called()

    def test_destroy_all(self, surfaces: SurfaceSet) -> None:
        """Closing tears down every surface."""
        surfaces.apply(scan(DP0, HDMI))
        surfaces.destroy_all()
        assert surfaces.names() == frozenset()


class TestTextMirror:
    """tk.Text has no textvariable, so it needs explicit mirroring."""

    def _widget(self, text: str = "") -> MagicMock:
        widget = MagicMock()
        state = {"text": text}
        widget.get.side_effect = lambda *_a: state["text"]
        widget.delete.side_effect = lambda *_a: state.update(text="")
        widget.insert.side_effect = lambda _i, value: state.update(text=value)
        widget._state = state
        return widget

    def test_typing_in_one_updates_the_other(self) -> None:
        """A key release in surface A reaches surface B."""
        a, b = self._widget("hello"), self._widget()
        var = MagicMock()
        var.get.return_value = "hello"
        mirror = TextMirror([a, b], var)
        event = MagicMock()
        event.widget = a
        mirror._on_key_release(event)
        var.set.assert_called_once_with("hello")
        assert b._state["text"] == "hello"

    def test_var_write_fans_out(self) -> None:
        """Setting the shared variable updates every widget."""
        a, b = self._widget(), self._widget()
        var = MagicMock()
        var.get.return_value = "typed"
        mirror = TextMirror([a, b], var)
        mirror._on_var_write("x", "", "w")
        assert a._state["text"] == "typed"
        assert b._state["text"] == "typed"

    def test_reentrancy_is_blocked(self) -> None:
        """A fan-out must not trigger another fan-out."""
        a = self._widget()
        var = MagicMock()
        var.get.return_value = "v"
        mirror = TextMirror([a], var)
        mirror._syncing = True
        mirror._on_var_write("x", "", "w")
        assert a._state["text"] == ""
        event = MagicMock()
        event.widget = a
        mirror._on_key_release(event)
        var.set.assert_not_called()

    def test_helper_returns_mirror(self) -> None:
        """The public helper wires the widgets up."""
        widget = self._widget()
        var = MagicMock()
        assert isinstance(mirror_text_widgets([widget], var), TextMirror)
        widget.bind.assert_called_once()


class TestSurfaceInfo:
    """SurfaceInfo equality drives the move-vs-noop decision."""

    def test_identical_infos_compare_equal(self) -> None:
        """Equality is by value, so an unchanged layout is a no-op."""
        rect = OutputRect(0, 0, 100, 100)
        first = SurfaceInfo("DP-0", rect, 0, is_primary=True)
        second = SurfaceInfo("DP-0", rect, 0, is_primary=True)
        assert first == second
