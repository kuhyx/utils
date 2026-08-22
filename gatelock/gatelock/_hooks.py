"""The callback interface an app embedding :class:`~gatelock.LockWindow` fills.

Split out of :mod:`gatelock._window` so the pure *interface* -- what an app
must implement -- can be read without the window mechanics that call it. This
module deliberately imports nothing from the runtime half, so an app can type
against the protocol without pulling in Tk window machinery.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import tkinter as tk

    from gatelock._surfaces import SurfaceInfo


class LockWindowHooks(Protocol):
    """Callbacks :class:`LockWindow` invokes; the embedding app supplies all."""

    def build_surface(self, parent: tk.Misc, surface: SurfaceInfo) -> None:
        """Build this app's widgets inside ``parent``, for one output.

        Called once per live output, and again whenever an output comes back.
        Tk variables should stay mastered on the root so every surface shows
        the same state, and every surface's submit path should call the same
        handler -- solving the lock on any monitor dismisses all of them.
        """

    def teardown_surface(self, surface: SurfaceInfo) -> None:
        """Forget per-surface state; that output went dark and is closing."""

    def on_focus_ready(self, surface: SurfaceInfo | None) -> None:
        """Called once the lock is mapped and (if applicable) grabbed.

        Args:
            surface: The surface that took initial focus, or None when no
                output is live and there is therefore nothing to focus.
        """

    def on_callback_error(self) -> None:
        """Called when a Tk callback raised (see :class:`~gatelock.GateRoot`)."""

    def on_close(self) -> None:
        """Called once, from :meth:`LockWindow.close`, before VT is restored.

        Runs on every exit path -- normal dismiss, SIGTERM, SIGINT -- not just
        a clean close, so app-specific teardown (restoring hardware state,
        etc.) can't be skipped by killing the process.
        """
