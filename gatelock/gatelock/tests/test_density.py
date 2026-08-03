"""Tests for the screen-height-derived compaction of the token scales."""

from __future__ import annotations

import tkinter as tk
import types

import pytest

from gatelock import LockConfig, _density


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """Each test resolves the factor from scratch."""
    _density.reset_cache()


@pytest.mark.parametrize(
    ("height", "expected"),
    [
        (2160, 1.0),
        (1080, 1.0),
        (900, 1.0),
        (768, 1.0),
        (767, 0.7),
        (600, 0.7),
        (0, 0.7),
    ],
)
def test_breakpoints(height: int, expected: float) -> None:
    """768px and up renders at full size; anything shorter is compacted."""
    assert _density.factor_for_height(height) == expected


def test_a_nonsense_height_does_not_compact() -> None:
    """A negative height is a Tk misreport, not a tiny screen.

    Compacting on it would shrink the UI of a machine nothing is known about;
    leaving it alone keeps the design-system size, which the fit check has
    actually verified.
    """
    assert _density.factor_for_height(-1) == 1.0


def test_forced_factor_applies_and_is_restored() -> None:
    """``forced`` is what lets a 1080p machine render a 768px layout."""
    with _density.forced(0.5):
        assert _density.density() == 0.5
        assert _density.scale_type(32) == 16
    _density.reset_cache()
    assert _density.density() != 0.5 or _density.factor_for_height(768) == 0.5


def test_type_never_shrinks_below_the_readable_floor() -> None:
    """Compaction may not push text under 11px, whatever the factor says."""
    with _density.forced(0.1):
        assert _density.scale_type(32) == 11
        assert _density.scale_type(12) == 11


def test_spacing_floor_and_zero() -> None:
    """A gap never collapses to nothing, but "no gap" stays no gap.

    Zero is a decision -- two labels deliberately touching -- so it must
    survive compaction unchanged, while a real gap keeps at least 2px or it
    stops reading as separation at all.
    """
    with _density.forced(0.1):
        assert _density.scale_space(48) == 5
        assert _density.scale_space(4) == 2
        assert _density.scale_space(0) == 0


def test_lockconfig_reads_through_the_scale() -> None:
    """The tokens themselves compact -- that is what reaches every widget."""
    config = LockConfig()
    with _density.forced(0.5):
        assert config.type_px("display") == 16
        assert config.space("xxl") == 24
        # font() applies Tk's negative-is-pixels convention on top.
        assert config.font("display", bold=True) == ("Arial", -16, "bold")


def test_a_non_numeric_screen_height_is_reported_not_trusted() -> None:
    """A faked tkinter returns a mock, not a height; that must not compact.

    The consuming apps replace ``tkinter`` wholesale in their test suites, so
    this is the shape ``density()`` sees there. Guessing a factor from a mock
    would silently resize every screen in a test run.
    """
    assert _density._usable_height(object()) is None
    assert _density._usable_height(768) == 768
    # bool is an int subclass, and a flag is not a screen height.
    flag = True
    assert _density._usable_height(flag) is None


def test_density_falls_back_to_full_size_without_a_display(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No display means no evidence, so nothing is compacted."""
    monkeypatch.setattr(_density, "_screen_height", lambda: None)
    assert _density.density() == 1.0


def test_density_reads_the_screen_and_caches_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The factor is resolved once: it is read for every font on every repaint."""
    calls: list[int] = []

    def _fake_height() -> int:
        calls.append(1)
        return 600

    monkeypatch.setattr(_density, "_screen_height", _fake_height)
    assert _density.density() == 0.7
    assert _density.density() == 0.7
    assert len(calls) == 1


def test_a_junk_override_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """A typo in the env var must not silently pick some other scale."""
    monkeypatch.setenv(_density.ENV_OVERRIDE, "big")
    monkeypatch.setattr(_density, "_screen_height", lambda: 1080)
    assert _density.density() == 1.0


class _StubRoot:
    """A Tk root stand-in that reports one height and records its teardown."""

    def __init__(self, height: int, destroyed: list[bool]) -> None:
        self._height = height
        self._destroyed = destroyed

    def winfo_screenheight(self) -> int:
        """Return the configured height."""
        return self._height

    def destroy(self) -> None:
        """Record that the probe root was cleaned up."""
        self._destroyed.append(True)


def test_probe_root_is_created_and_destroyed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no root yet, the factor is read from a throwaway one.

    The apps build their ``LockConfig`` at import time, before any Tk root
    exists, so this is the normal path -- and the probe must not survive it.
    """
    destroyed: list[bool] = []
    stub = types.SimpleNamespace(
        _default_root=None,
        Tk=lambda: _StubRoot(600, destroyed),
        TclError=tk.TclError,
    )
    monkeypatch.setattr(_density, "tk", stub)
    assert _density._screen_height() == 600
    assert destroyed == [True]


def test_no_display_leaves_the_scale_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """A headless run cannot size anything, and must say so rather than guess."""

    message = "no display name and no $DISPLAY environment variable"

    def _no_display() -> None:
        raise tk.TclError(message)

    stub = types.SimpleNamespace(
        _default_root=None, Tk=_no_display, TclError=tk.TclError
    )
    monkeypatch.setattr(_density, "tk", stub)
    assert _density._screen_height() is None


def test_forced_restores_a_pre_existing_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nesting must not clobber a factor the caller had already forced."""
    monkeypatch.setenv(_density.ENV_OVERRIDE, "0.9")
    with _density.forced(0.5):
        assert _density.density() == 0.5
    assert _density.density() == 0.9


def test_an_existing_root_is_asked_rather_than_a_new_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a root already up, the factor comes from it -- no second Tk.

    The apps that build their LockConfig lazily hit this path, and creating a
    throwaway Tk alongside a live lock window is not something to do casually.
    """
    destroyed: list[bool] = []
    stub = types.SimpleNamespace(
        _default_root=_StubRoot(768, destroyed),
        Tk=None,
        TclError=tk.TclError,
    )
    monkeypatch.setattr(_density, "tk", stub)

    assert _density._screen_height() == 768
    assert destroyed == []
