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

from gatelock._window import LockConfig, LockWindow

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def mock_root() -> MagicMock:
    """A MagicMock standing in for a tkinter root window."""
    root = MagicMock()
    root.winfo_screenwidth.return_value = 1920
    root.winfo_screenheight.return_value = 1080
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
