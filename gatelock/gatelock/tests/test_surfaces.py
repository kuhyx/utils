"""Tests for the surface set: one lock window per live output."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gatelock._outputs import Output, OutputRect, OutputScan
from gatelock._surfaces import (
    SurfaceInfo,
    SurfaceSet,
    TextMirror,
    mirror_text_widgets,
    needs_backdrop_root,
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


class TestNeedsBackdropRoot:
    """The predicate that must NOT be simplified to `iff overrideredirect`."""

    @pytest.mark.parametrize(
        ("config", "expected"),
        [
            (LockConfig(mode="hard"), True),
            (LockConfig(mode="soft"), False),
            (LockConfig(mode="soft", grab="global"), True),
            (LockConfig(mode="soft", grab="local"), True),
            (LockConfig(mode="hard", overrideredirect=False, grab="none"), False),
        ],
    )
    def test_predicate(self, config: LockConfig, *, expected: bool) -> None:
        """A global grab needs a viewable root even without overrideredirect."""
        assert needs_backdrop_root(config) is expected


class TestApply:
    """Bringing the surface set in line with a scan."""

    def test_creates_one_per_live_output(self, surfaces: SurfaceSet) -> None:
        """Each live output gets its own window at its own rectangle."""
        delta = surfaces.apply(scan(DP0, HDMI))
        assert sorted(delta.created) == ["DP-0", "HDMI-0"]
        assert delta.changed is True
        infos = surfaces.infos()
        assert [i.output_name for i in infos] == ["DP-0", "HDMI-0"]
        assert infos[0].rect == OutputRect(0, 0, 3840, 2160)
        assert infos[0].is_primary is True

    def test_skips_dark_outputs(self, surfaces: SurfaceSet) -> None:
        """A connected-but-modeless output gets no surface."""
        surfaces.apply(scan(DP0_DARK, HDMI))
        assert sorted(surfaces.names()) == ["HDMI-0"]

    def test_removes_surface_when_output_goes_dark(self, surfaces: SurfaceSet) -> None:
        """Losing a mode tears that surface down and tells the app."""
        surfaces.apply(scan(DP0, HDMI))
        builder = surfaces._builder
        delta = surfaces.apply(scan(DP0_DARK, HDMI))
        assert delta.removed == ("DP-0",)
        assert sorted(surfaces.names()) == ["HDMI-0"]
        builder.teardown_surface.assert_called_once()

    def test_moves_in_place_rather_than_recreating(self, surfaces: SurfaceSet) -> None:
        """A resolution change must not discard half-typed input."""
        surfaces.apply(scan(DP0))
        builder = surfaces._builder
        builder.build_surface.reset_mock()
        delta = surfaces.apply(scan(DP0_MOVED))
        assert delta.moved == ("DP-0",)
        assert delta.created == ()
        builder.build_surface.assert_not_called()
        assert surfaces.infos()[0].rect == OutputRect(0, 0, 1920, 1080)

    def test_unchanged_layout_is_a_noop(self, surfaces: SurfaceSet) -> None:
        """Re-applying the same scan changes nothing (Configure-storm guard)."""
        surfaces.apply(scan(DP0, HDMI))
        delta = surfaces.apply(scan(DP0, HDMI))
        assert delta.changed is False

    def test_zero_live_outputs_removes_everything(self, surfaces: SurfaceSet) -> None:
        """All dark: no surfaces, and nothing blind (there is nothing to see)."""
        surfaces.apply(scan(DP0, HDMI))
        delta = surfaces.apply(scan(DP0_DARK))
        assert sorted(delta.removed) == ["DP-0", "HDMI-0"]
        assert surfaces.names() == frozenset()
        assert delta.unverified == ()


class TestVerify:
    """The blind-output alarm."""

    def test_nothing_blind_when_all_mapped(self, surfaces: SurfaceSet) -> None:
        """A mapped surface on every live output means nothing is blind."""
        delta = surfaces.apply(scan(DP0, HDMI))
        assert delta.unverified == ()

    def test_unmapped_surface_is_blind(self, surfaces: SurfaceSet) -> None:
        """A live output whose window is unmapped is reported."""
        surfaces.apply(scan(DP0))
        surfaces._surfaces["DP-0"].window.withdraw()
        assert surfaces.verify() == ("DP-0",)

    def test_missing_surface_is_blind(self, surfaces: SurfaceSet) -> None:
        """A live output with no surface at all is reported."""
        assert surfaces.verify(live_names=frozenset({"DP-0"})) == ("DP-0",)


class TestEnforce:
    """Re-assertion only ever adds visibility."""

    def test_remaps_an_unmapped_surface(self, surfaces: SurfaceSet) -> None:
        """An unmapped surface is deiconified again."""
        surfaces.apply(scan(DP0))
        window = surfaces._surfaces["DP-0"].window
        window.withdraw()
        assert surfaces.enforce() == ("DP-0",)
        assert window.winfo_ismapped() is True

    def test_corrects_drifted_geometry(self, surfaces: SurfaceSet) -> None:
        """A surface moved by something else is put back."""
        surfaces.apply(scan(DP0))
        window = surfaces._surfaces["DP-0"].window
        window.geometry("100x100+50+50")
        assert surfaces.enforce() == ("DP-0",)
        assert window.winfo_width() == 3840

    def test_stable_surface_needs_no_correction(self, surfaces: SurfaceSet) -> None:
        """A correct surface reports nothing, but is still raised."""
        surfaces.apply(scan(DP0))
        assert surfaces.enforce() == ()
        surfaces._surfaces["DP-0"].window.lift.assert_called()

    def test_soft_mode_does_not_reassert_overrideredirect(
        self, mock_root: MagicMock
    ) -> None:
        """A managed window must not be forced override-redirect."""
        soft = SurfaceSet(mock_root, LockConfig(mode="soft"), MagicMock())
        soft.apply(scan(DP0))
        soft.enforce()
        soft._surfaces["DP-0"].window.overrideredirect.assert_not_called()

    def test_raise_all(self, surfaces: SurfaceSet) -> None:
        """Every surface can be lifted at once."""
        surfaces.apply(scan(DP0, HDMI))
        surfaces.raise_all()
        for surface in surfaces._surfaces.values():
            surface.window.lift.assert_called()


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
