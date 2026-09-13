# Copyright (c) 2026 Krzysztof Rudnicki
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

The clock does not gate arming either (2026-09-13). The wait used to give up
after 60 s, and a boot-time ``Persistent=true`` catch-up starts one second
after the user manager, long before X exists: on a slow boot the deadline
passed, the unit exited, and nothing locked until the next timer slot -- which
systemd had already marked as fired. No X server means the user cannot use the
machine either, so waiting forever costs nothing and cannot be a bypass. The
wait now polls until the server answers and re-states itself at WARNING every
five minutes, so ``systemctl status`` never shows a healthy, silent unit.
"""

from __future__ import annotations

import logging
import os
import sys
import time
import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL_S = 1.0
# How often a still-missing X server is re-stated at WARNING. Same reasoning
# as ``_queue.QUEUE_HEARTBEAT_SECONDS``: a long silent wait is
# indistinguishable from a hung unit.
X_WAIT_HEARTBEAT_S = 300.0


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
    timeout_s: float | None = None,
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
        timeout_s: Give up after this long. ``None`` (the default) waits for
            as long as it takes; see the module docstring for why a bound is
            the wrong tool here.
        interval_s: Seconds between attempts.
        sleep: Injected for tests.
        monotonic: Injected for tests.
        probe: Injected for tests; defaults to opening a throwaway Tk root.

    Returns:
        True once an X server answered, False only if ``timeout_s`` was set
        and passed.
    """
    attempt = probe if probe is not None else _probe_x_server
    started = monotonic()
    next_heartbeat = X_WAIT_HEARTBEAT_S
    while True:
        if attempt():
            elapsed = monotonic() - started
            if elapsed >= interval_s:
                _logger.warning("X server answered after %.0fs; arming now", elapsed)
            return True
        elapsed = monotonic() - started
        if timeout_s is not None and elapsed >= timeout_s:
            _logger.error(
                "no X server answered within %.0fs; cannot build a lock window",
                timeout_s,
            )
            return False
        if elapsed >= next_heartbeat:
            _logger.warning(
                "no X server on %s after %.0fs -- still waiting, nothing is locked",
                os.environ.get("DISPLAY", "<unset>"),
                elapsed,
            )
            while next_heartbeat <= elapsed:
                next_heartbeat += X_WAIT_HEARTBEAT_S
        sleep(interval_s)


def _probe_x_server() -> bool:
    """Whether a throwaway Tk root can be created and destroyed."""
    try:
        root = tk.Tk()
    except tk.TclError:
        return False
    root.destroy()
    return True
