# Copyright (c) 2026 Krzysztof Rudnicki
"""Report every error and every wait over 1 s of a Tk (or any Python) app.

The Python reporter of kuhy's shared app-errors pipeline (utils
``DOCS-app-errors.md``; the Dart one is crdt_sync_flutter's, generalised from
kartka). ``install`` once at start-up hooks ``sys.excepthook``,
``threading.excepthook`` and Tk callback errors (``Misc._report_exception``,
which every root, ``GateRoot`` included, goes through), each chained to the
hook it replaces. ``Reporter.begin``/``wait`` time a user-visible wait, and
``watch_stalls`` reports a frozen Tk loop with no call-site work.

A report is one JSON line in ``$XDG_STATE_HOME/app-errors-spool/<app>.jsonl``
(``gatelock._error_spool``). The PC's ``app-errors`` ingest (utils
``app_errors/``) groups it by signature and hands it to the board, which files
a ticket. Reporting shows nothing on screen and never raises.
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
import sys
import threading
import tkinter as tk
from typing import TYPE_CHECKING

from gatelock._error_spool import SLOW_KIND, Reporter, SlowWait

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

__all__ = [
    "SLOW_KIND",
    "STALL_TICK_MS",
    "Reporter",
    "SlowWait",
    "install",
    "watch_stalls",
]

#: How often the stall watch ticks, milliseconds.
STALL_TICK_MS = 100

_TK_DOOR = "_report_exception"


@dataclass
class _Installed:
    """The process's reporter once ``install`` ran (tests put their own here)."""

    reporter: Reporter | None = None


INSTALLED = _Installed()


def watch_stalls(root: tk.Misc, reporter: Reporter) -> None:
    """Report each time ``root``'s event loop froze past the threshold.

    The operation is ``tk.mainloop``: a blocking call on the Tk thread.
    """
    last = [reporter.clock()]

    def tick() -> None:
        now = reporter.clock()
        late = round((now - last[0]) * 1000) - STALL_TICK_MS
        last[0] = now
        if late > reporter.threshold * 1000:
            reporter.slow("tk.mainloop", late, wait_id=f"stall-{int(now * 1000):x}")
        with suppress(tk.TclError):  # the window is gone: the watch ends
            root.after(STALL_TICK_MS, tick)

    root.after(STALL_TICK_MS, tick)


def install(
    app: str,
    repo: str,
    *,
    mark: str = "",
    build: int = 0,
    version: str | None = None,
) -> Reporter:
    """Hook uncaught, thread and Tk callback errors once; return the reporter.

    The spool is ``$XDG_STATE_HOME/app-errors-spool``; tests build a
    ``Reporter`` with their own ``spool`` instead.
    """
    # One set of process-wide hooks; a test pre-installs its own reporter by
    # setting INSTALLED.reporter, and no hook is touched.
    if INSTALLED.reporter is not None:
        return INSTALLED.reporter
    rep = Reporter(
        app=app,
        repo=repo,
        mark=mark,
        build=build,
        version=version,
    )
    prior_sys = sys.excepthook

    def sys_hook(
        kind: type[BaseException], value: BaseException, tb: TracebackType | None
    ) -> None:
        rep.report("uncaught.python", value, tb)
        prior_sys(kind, value, tb)

    prior_thread = threading.excepthook

    def thread_hook(args: threading.ExceptHookArgs) -> None:
        value: object = args.exc_value
        if value is None:
            value = args.exc_type.__name__
        rep.report("uncaught.thread", value, args.exc_traceback)
        prior_thread(args)

    # Misc._report_exception is the one door every Tk callback error passes,
    # whatever root subclass overrides report_callback_exception.
    prior_tk: Callable[[tk.Misc], None] = getattr(tk.Misc, _TK_DOOR)

    def tk_hook(widget: tk.Misc) -> None:
        _, value, tb = sys.exc_info()
        if value is not None:
            rep.report("uncaught.tk", value, tb)
        prior_tk(widget)

    sys.excepthook = sys_hook
    threading.excepthook = thread_hook
    setattr(tk.Misc, _TK_DOOR, tk_hook)
    INSTALLED.reporter = rep
    return rep
