"""Safety guards shared by every locker app.

Both guards here were duplicated across the consuming repos (and one of them
was missing from ``wake_alarm`` entirely, which is exactly the kind of drift a
shared library exists to stop).

The second one, :func:`wait_for_x_server`, changed meaning when it moved here,
and the change is the point. Its ancestor gated *whether to arm at all*: on a
boot where the display was not ready it logged "will retry on the next timer
tick" and exited without locking. Combined with a monitor that came up
modeless, that left the machine unlocked until the next tick.

So the rule now is: **output count never gates arming.** Zero live outputs
means lock without showing, not decline to lock. This function may only answer
"can we talk to an X server at all", because without one there is no Tk and
genuinely nothing to do. It must never ask how many outputs are live.
"""

from __future__ import annotations

import logging
import sys
import time
import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S = 60.0
_DEFAULT_INTERVAL_S = 1.0


def assert_not_under_pytest(what: str) -> None:
    """Refuse to build a real lock window inside a test run.

    A lock window takes a global input grab and covers every screen. One built
    by accident during a test run would black out the developer's machine, so
    this fails loudly instead.

    Call this from an app's entry point, never from inside gatelock: gatelock's
    own tests mock the Tk *root* rather than the ``tkinter`` module, so the
    check would fire throughout its own suite.

    Args:
        what: Name of the thing being built, for the error message.

    Raises:
        RuntimeError: If pytest is running with a real ``tkinter``.
    """
    if "pytest" not in sys.modules:
        return
    if getattr(tk, "__name__", "") != "tkinter":
        # tkinter is mocked, so no real window can appear. This is the normal
        # path for a properly-isolated test.
        return
    message = (
        f"refusing to build {what} under pytest with real tkinter -- "
        "this would grab the input of the machine running the tests"
    )
    raise RuntimeError(message)


def wait_for_x_server(
    *,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
    interval_s: float = _DEFAULT_INTERVAL_S,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    probe: Callable[[], bool] | None = None,
) -> bool:
    """Wait until an X server will accept a connection.

    Absorbs the cold-boot race where a unit starts before the display manager
    has finished. It asks one question only -- is there an X server -- and
    deliberately says nothing about whether any monitor is lit. A dark screen
    is a reason to lock silently, never a reason to skip locking.

    Args:
        timeout_s: Give up after this long.
        interval_s: Seconds between attempts.
        sleep: Injected for tests.
        monotonic: Injected for tests.
        probe: Injected for tests; defaults to opening a throwaway Tk root.

    Returns:
        True if an X server answered, False on timeout.
    """
    attempt = probe if probe is not None else _probe_x_server
    deadline = monotonic() + timeout_s
    while True:
        if attempt():
            return True
        if monotonic() >= deadline:
            _logger.error(
                "no X server answered within %.0fs; cannot build a lock window",
                timeout_s,
            )
            return False
        sleep(interval_s)


def _probe_x_server() -> bool:
    """Whether a throwaway Tk root can be created and destroyed."""
    try:
        root = tk.Tk()
    except tk.TclError:
        return False
    root.destroy()
    return True
