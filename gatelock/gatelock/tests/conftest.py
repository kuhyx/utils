"""Shared fixtures for gatelock tests.

``LockWindow`` takes its Tk root as a constructor argument (composition, not
inheritance), so tests never need a real display -- a plain ``MagicMock``
stands in for the root everywhere. ``GateRoot`` does subclass ``tk.Tk``
directly (that's the point: Tkinter calls ``report_callback_exception`` on
the real root), so its tests build an instance via ``__new__`` to exercise
the overridden method without running ``tk.Tk.__init__`` (which requires a
display).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from gatelock._outputs import Output, OutputRect, OutputScan
from gatelock._recovery import RecoveryCollaborators, RecoveryLoop
from gatelock._surfaces import SurfaceSet
from gatelock._window import LockConfig, LockWindow

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


DEFAULT_OUTPUTS = (
    Output(
        "VIRTUAL-1", connected=True, rect=OutputRect(0, 0, 1920, 1080), primary=True
    ),
)
"""One live output matching ``mock_root``'s screen size."""


def make_toplevel(_parent: object = None, **_kwargs: object) -> MagicMock:
    """A Toplevel stand-in that remembers the geometry it was given.

    Real ``tk.Toplevel`` cannot be constructed over a ``MagicMock`` master --
    tkinter's widget-naming path recurses through the mock forever and the test
    run hangs rather than failing. So every surface window is faked here.
    """
    win = MagicMock()
    state = {"x": 0, "y": 0, "w": 0, "h": 0, "mapped": False}

    def geometry(spec: str) -> None:
        size, x, y = spec.split("+")
        width, height = size.split("x")
        state.update(x=int(x), y=int(y), w=int(width), h=int(height))

    win.geometry.side_effect = geometry
    win.deiconify.side_effect = lambda: state.update(mapped=True)
    win.withdraw.side_effect = lambda: state.update(mapped=False)
    win.winfo_ismapped.side_effect = lambda: state["mapped"]
    win.winfo_rootx.side_effect = lambda: state["x"]
    win.winfo_rooty.side_effect = lambda: state["y"]
    win.winfo_width.side_effect = lambda: state["w"]
    win.winfo_height.side_effect = lambda: state["h"]
    return win


@pytest.fixture(autouse=True)
def _hermetic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[None]:
    """Keep the whole suite off the real machine.

    Autouse and deliberately broad. A lock window takes a global input grab and
    disables VT switching; a test that reached the real display or the real
    ``setxkbmap`` would black out the developer's own machine, and one that
    reached the real runtime directory could stand a *production* locker down.
    Blocking all of that centrally beats remembering to patch it per test.
    """
    monkeypatch.setenv("GATELOCK_RUNTIME_DIR", str(tmp_path / "runtime"))
    with (
        patch("gatelock._surfaces.tk.Toplevel", side_effect=make_toplevel),
        patch("gatelock._outputs.RandrBackend.create", return_value=None),
        patch("gatelock._outputs.scan_xrandr", return_value=DEFAULT_OUTPUTS),
        patch("gatelock._detect._RandrEventSource.start", return_value=False),
        patch("gatelock._vt.shutil.which", return_value="/usr/bin/setxkbmap"),
        patch("gatelock._vt.subprocess.run"),
    ):
        yield


@pytest.fixture
def mock_root() -> MagicMock:
    """A MagicMock standing in for a tkinter root window."""
    root = MagicMock()
    root.winfo_screenwidth.return_value = 1920
    root.winfo_screenheight.return_value = 1080
    root.grab_current.return_value = root
    return root


@pytest.fixture
def mock_subprocess_run() -> Generator[MagicMock]:
    """Block real subprocess calls (setxkbmap) and fake its presence."""
    with (
        patch("gatelock._vt.shutil.which", return_value="/usr/bin/setxkbmap"),
        patch("gatelock._vt.subprocess.run") as mock,
    ):
        yield mock


def make_window(
    root: MagicMock,
    *,
    config: LockConfig | None = None,
    hooks: MagicMock | None = None,
) -> tuple[LockWindow, MagicMock]:
    """Build a LockWindow over a mock root, returning it with its hooks mock."""
    hooks = hooks if hooks is not None else MagicMock()
    window = LockWindow(root, config or LockConfig(), hooks)
    return window, hooks


DP0 = Output("DP-0", connected=True, rect=OutputRect(0, 0, 3840, 2160), primary=True)
HDMI = Output("HDMI-0", connected=True, rect=OutputRect(3840, 0, 2560, 1440))
DP0_DARK = Output("DP-0", connected=True, rect=None, primary=True)
HDMI_DARK = Output("HDMI-0", connected=True, rect=None)

BOTH = OutputScan((DP0, HDMI), "randr", ok=True)
DEAD_PRIMARY = OutputScan((DP0_DARK, HDMI), "randr", ok=True)
ALL_DARK = OutputScan((DP0_DARK, HDMI_DARK), "randr", ok=True)
FAILED = OutputScan((), "none", ok=False)


def build_loop(
    root: MagicMock, config: LockConfig
) -> tuple[RecoveryLoop, MagicMock, SurfaceSet]:
    """A recovery loop over mocked surroundings, for an arbitrary config.

    Args:
        root: The mocked Tk root the loop drives.
        config: The lock configuration under test.

    Returns:
        The loop, its mocked enumerator, and the surface set it manages.
    """
    hooks = MagicMock()
    surfaces = SurfaceSet(root, config, hooks)
    enumerator = MagicMock()
    return (
        RecoveryLoop(
            root,
            RecoveryCollaborators(
                config=config,
                surfaces=surfaces,
                enumerator=enumerator,
                detector=MagicMock(),
                hooks=hooks,
            ),
        ),
        enumerator,
        surfaces,
    )


@pytest.fixture
def loop(mock_root: MagicMock) -> tuple[RecoveryLoop, MagicMock, SurfaceSet]:
    """A recovery loop in hard mode, the configuration most tests want."""
    return build_loop(mock_root, LockConfig(mode="hard"))
