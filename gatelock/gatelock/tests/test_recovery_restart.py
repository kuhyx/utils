# Copyright (c) 2026 Krzysztof Rudnicki
"""An output that comes up while the recovery loop is stopped is covered on restart.

leetcode-guard's study mode stops the recovery loop and the change detector on
purpose. On 2026-11-11 the 4K output (DP-2) only got a mode 3m20s after the
lock armed -- long after study mode had stopped both -- so the backdrop stayed
6400x1440 and no surface was built for it. That is the stopped loop doing what
it was told, not a detection bug: this pins that the FIRST tick after
``start()`` sizes the backdrop to the new screen and builds the missing surface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gatelock._config import LockConfig
from gatelock._outputs import OutputScan
from gatelock.tests.conftest import BOTH, HDMI, build_loop

if TYPE_CHECKING:
    from unittest.mock import MagicMock

HDMI_ONLY = OutputScan((HDMI,), "randr", ok=True)


def test_output_that_appeared_while_stopped_is_covered_on_restart(
    mock_root: MagicMock,
) -> None:
    """Stop, grow the screen, start: one tick later the new output is locked."""
    recovery, enumerator, surfaces = build_loop(mock_root, LockConfig(mode="hard"))
    enumerator.scan.return_value = HDMI_ONLY
    mock_root.winfo_screenheight.return_value = 1440
    recovery.tick()
    assert surfaces.names() == {"HDMI-0"}

    recovery.stop()
    enumerator.scan.return_value = BOTH  # DP-0 is the 4K output here
    mock_root.winfo_screenwidth.return_value = 6400
    mock_root.winfo_screenheight.return_value = 2160
    recovery.tick()  # study mode off: the first tick after start() is this one

    assert surfaces.names() == {"DP-0", "HDMI-0"}
    mock_root.geometry.assert_called_with("6400x2160+0+0")
