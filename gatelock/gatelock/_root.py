"""Safe Tk root window that never lets a callback exception escape."""

from __future__ import annotations

import logging
import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

_logger = logging.getLogger(__name__)


class GateRoot(tk.Tk):
    """Tk root that routes callback errors to a handler instead of crashing.

    Overriding ``report_callback_exception`` is the idiomatic, blind-except-free
    way to guarantee that no exception raised inside a Tk callback escapes the
    event loop -- essential while a global input grab is held, since a crashed
    mainloop would leave the screen grabbed with no way to release it.
    """

    on_callback_error: Callable[[], None] | None = None

    def report_callback_exception(
        self,
        exc: type[BaseException],
        val: BaseException,
        tb: TracebackType | None,
    ) -> None:
        """Log a callback error and notify the handler; never re-raise."""
        _logger.error("gatelock callback error", exc_info=(exc, val, tb))
        if self.on_callback_error is not None:
            self.on_callback_error()
