"""Tests for the surface set: one lock window per live output."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gatelock._outputs import Output, OutputRect, OutputScan
from gatelock._surfaces import (
    SurfaceSet,
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
