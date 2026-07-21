"""Fullscreen lock window: setup, input grab, VT-disable, safe lifecycle.

Generalizes the window mechanics that wake_alarm, screen-locker, and
diet_guard each implemented separately. The three differ along independent
axes (whether the window is WM-unmanaged, what kind of input grab is taken,
whether VT switching is disabled, how a failed global grab is retried) --
:class:`LockConfig` exposes each axis explicitly, with ``mode`` as a
convenience preset, so one class can reproduce all three projects' existing
behavior exactly.
"""

from __future__ import annotations

import atexit
import contextlib
from dataclasses import dataclass
import logging
import signal
import tkinter as tk
from typing import TYPE_CHECKING, Literal, Protocol

from gatelock._vt import disable_vt_switching, restore_vt_switching

if TYPE_CHECKING:
    from types import FrameType

_logger = logging.getLogger(__name__)

GrabKind = Literal["none", "local", "global"]
LockMode = Literal["soft", "hard"]

# Periodic no-op so a grabbed, event-starved loop keeps handing control back
# to Python, letting SIGTERM/SIGINT be serviced promptly.
_KEEPALIVE_MS = 250
# Default retry interval for a "global" grab that initially fails (e.g. a
# fullscreen game holds it). Used whenever grab_retry_ms is left unset.
_DEFAULT_GRAB_RETRY_MS = 200


@dataclass(frozen=True)
class LockConfig:
    """Declarative knobs for one :class:`LockWindow` instance.

    Each field left as ``None`` is derived from ``mode``; an explicit value
    always overrides the preset for that one axis.

    Attributes:
        mode: Preset bundling the common combination. "soft" = topmost only,
            typeable, WM-escapable (today's wake_alarm). "hard" =
            overrideredirect + global grab + VT-disable (today's diet_guard
            and screen-locker production lock).
        overrideredirect: Force a WM-unmanaged window. None = derive from mode.
        grab: Input grab strategy. None = derive from mode.
        disable_vt: Disable Ctrl+Alt+Fn VT switching. None = derive from mode.
        grab_retry_ms: Retry interval in ms for a "global" grab that initially
            fails. 0 means "try once, then fall back to a local grab" (the
            original screen-locker behavior). Left unset (None), a "global"
            grab retries forever every 200ms until it succeeds (the
            diet_guard behavior, robust to e.g. a fullscreen game holding the
            grab) -- there is no give-up/fallback in that case.
        grab_log_every: Log a warning every N failed retry-forever attempts.
        bg: Background color for the root window.
        fg: Primary (near-white) text color.
        muted: Secondary/caption text color.
        field_bg: Background for "raised" surfaces (entry/spinbox fields,
            input wells) -- one step lighter than ``bg``.
        accent: The shared brand accent (buttons, primary actions).
        success: Positive/on-track status color.
        warning: Caution/pending status color.
        danger: Negative/error status color.
        on_fill: Text/icon color for anything drawn on top of a filled
            accent/success/warning/danger surface (e.g. a button's label) --
            NOT ``fg``. All four fills sit in the same mid-light band, so
            near-white text under-contrasts on every one of them; callers
            must pick ``fg`` vs. ``on_fill`` based on the widget's own
            background, never hardcode one for all buttons.
        font_family: Default font family for lock-window widgets.

    All color/font defaults come from the ``unified-design-system`` skill
    (``~/.claude/skills/unified-design-system/references/tokens.md``) -- the
    same palette used by every one of kuhy's apps, Flutter and web included.
    screen-locker, wake_alarm, and diet_guard should read these fields
    instead of re-hardcoding their own hex/font literals.
    """

    mode: LockMode = "hard"
    overrideredirect: bool | None = None
    grab: GrabKind | None = None
    disable_vt: bool | None = None
    grab_retry_ms: int | None = None
    grab_log_every: int = 25
    bg: str = "#211D1B"
    fg: str = "#ECEAE9"
    muted: str = "#AAA09A"
    field_bg: str = "#2B2624"
    accent: str = "#B8862E"
    success: str = "#8A9A3C"
    warning: str = "#E0A63C"
    danger: str = "#E2585F"
    on_fill: str = "#211D1B"
    font_family: str = "Arial"

    def resolved_overrideredirect(self) -> bool:
        """Return the effective overrideredirect setting."""
        if self.overrideredirect is not None:
            return self.overrideredirect
        return self.mode == "hard"

    def resolved_grab(self) -> GrabKind:
        """Return the effective grab strategy."""
        if self.grab is not None:
            return self.grab
        return "global" if self.mode == "hard" else "none"

    def resolved_disable_vt(self) -> bool:
        """Return whether VT switching should be disabled."""
        if self.disable_vt is not None:
            return self.disable_vt
        return self.mode == "hard"


class LockWindowHooks(Protocol):
    """Callbacks :class:`LockWindow` invokes; the embedding app supplies all."""

    def on_focus_ready(self) -> None:
        """Called once the window is mapped and (if applicable) grabbed.

        The app should focus its first input widget here.
        """

    def on_callback_error(self) -> None:
        """Called when a Tk callback raised (see :class:`~gatelock.GateRoot`)."""

    def on_close(self) -> None:
        """Called once, from :meth:`LockWindow.close`, before VT is restored.

        Runs on every exit path -- normal dismiss, SIGTERM, SIGINT -- not just
        a clean close, so app-specific teardown (restoring hardware state,
        etc.) can't be skipped by killing the process.
        """


class LockWindow:
    """Fullscreen window setup, input grab, and exit-path lifecycle."""

    def __init__(
        self,
        root: tk.Tk,
        config: LockConfig,
        hooks: LockWindowHooks,
    ) -> None:
        """Initialize the lock window wrapper.

        Args:
            root: The Tk root to configure and own the lifecycle of.
            config: Declarative lock behavior for this instance.
            hooks: App-supplied callbacks for focus, errors, and teardown.
        """
        self.root = root
        self._config = config
        self._hooks = hooks
        self._vt_disabled = False
        self._closed = False

    # -- window mechanics -----------------------------------------------------

    def setup(self) -> None:
        """Configure the lock window per the resolved config."""
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.root.geometry(f"{screen_w}x{screen_h}+0+0")
        self.root.attributes(topmost=True)
        self.root.configure(bg=self._config.bg, cursor="arrow")
        if self._config.resolved_overrideredirect():
            self.root.overrideredirect(boolean=True)
        self.root.attributes(fullscreen=True)
        if self._config.resolved_disable_vt():
            self._vt_disabled = disable_vt_switching()

    def grab_input(self) -> None:
        """Force focus to the window, then acquire the configured grab."""
        self.root.update_idletasks()
        self.root.focus_force()
        grab = self._config.resolved_grab()
        if grab == "global":
            self._acquire_global_grab(attempt=1)
        elif grab == "local":
            with contextlib.suppress(tk.TclError):
                self.root.grab_set()
        self.root.after(100, self._notify_focus_ready)

    def _acquire_global_grab(self, *, attempt: int) -> None:
        """Acquire the global input grab, retrying per ``grab_retry_ms``.

        Args:
            attempt: 1-based attempt counter, used only to throttle the log.
        """
        retry_ms = self._config.grab_retry_ms
        try:
            self.root.grab_set_global()
        except tk.TclError:
            if retry_ms == 0:
                _logger.warning("Global grab failed, falling back to local grab")
                with contextlib.suppress(tk.TclError):
                    self.root.grab_set()
                return
            effective_retry_ms = retry_ms or _DEFAULT_GRAB_RETRY_MS
            if not attempt % self._config.grab_log_every:
                _logger.warning(
                    "global grab still blocked after %d attempts (another "
                    "app -- e.g. a fullscreen game -- holds it); waiting "
                    "for it to free",
                    attempt,
                )
            self.root.after(
                effective_retry_ms,
                lambda: self._acquire_global_grab(attempt=attempt + 1),
            )
            return
        with contextlib.suppress(tk.TclError):
            self.root.focus_force()
            self._notify_focus_ready()

    def _notify_focus_ready(self) -> None:
        """Tell the app it can focus its first input widget now."""
        with contextlib.suppress(tk.TclError):
            self._hooks.on_focus_ready()

    # -- lifecycle --------------------------------------------------------

    def _install_signal_handlers(self) -> None:
        """Ensure VT switching is restored on crash or kill, not just close."""
        atexit.register(self._restore_vt)
        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(ValueError):
                signal.signal(sig, self._on_signal)

    def _on_signal(self, _signum: int, _frame: FrameType | None) -> None:
        """Raise so SIGTERM/SIGINT unwind through run()'s try/finally."""
        raise SystemExit(0)

    def _keepalive(self) -> None:
        """Re-arm a periodic no-op so pending signals get serviced promptly."""
        with contextlib.suppress(tk.TclError):
            self.root.after(_KEEPALIVE_MS, self._keepalive)

    def _restore_vt(self) -> None:
        """Restore VT switching; idempotent, safe to call on any exit path."""
        if not self._vt_disabled:
            return
        restore_vt_switching()
        self._vt_disabled = False

    def close(self) -> None:
        """Run app teardown, restore VT switching, destroy the window.

        Idempotent -- safe to call directly (normal dismiss) and again from
        :meth:`run`'s ``finally`` (crash/signal exit) without double-running
        app teardown.
        """
        if self._closed:
            return
        self._closed = True
        self._hooks.on_close()
        self._restore_vt()
        with contextlib.suppress(tk.TclError):
            self.root.destroy()

    def run(self) -> None:
        """Run the Tk mainloop, guaranteeing cleanup on every exit path."""
        self._install_signal_handlers()
        self._keepalive()
        try:
            self.root.mainloop()
        finally:
            self.close()
