"""Lock window orchestration: surfaces, input grab, VT-disable, safe lifecycle.

Generalizes the window mechanics that wake_alarm, screen-locker, and
diet_guard each implemented separately. The three differ along independent
axes (whether the window is WM-unmanaged, what kind of input grab is taken,
whether VT switching is disabled, how a failed global grab is retried) --
:class:`LockConfig` exposes each axis explicitly, with ``mode`` as a
convenience preset, so one class can reproduce all three projects' existing
behavior exactly.

Since v0.2.0 this module only *orchestrates*. Enumeration lives in
:mod:`gatelock._outputs`, windows in :mod:`gatelock._surfaces`, change
detection in :mod:`gatelock._detect`, re-assertion in
:mod:`gatelock._recovery`, and cross-app priority in
:mod:`gatelock._arbiter`.

Arming order matters and is deliberate: **arm first, render second.** The grab
and the VT-disable happen regardless of how many outputs are live, and the
surfaces are then built for whatever the user can actually see -- possibly
nothing. Zero live outputs means "lock without showing", never "decline to
lock". The inverse of that rule is what left the machine unlocked on
2026-07-25.
"""

from __future__ import annotations

import atexit
import contextlib
from dataclasses import dataclass
import logging
import signal
import tkinter as tk
from typing import TYPE_CHECKING, Literal, Protocol

from gatelock._arbiter import RANK_SCREEN_LOCKER
from gatelock._detect import OutputChangeDetector
from gatelock._outputs import OutputEnumerator
from gatelock._recovery import RecoveryLoop
from gatelock._surfaces import SurfaceSet, needs_backdrop_root
from gatelock._vt import disable_vt_switching, restore_vt_switching

if TYPE_CHECKING:
    from types import FrameType

    from gatelock._arbiter import Arbiter
    from gatelock._surfaces import SurfaceInfo

_logger = logging.getLogger(__name__)

GrabKind = Literal["none", "local", "global"]
LockMode = Literal["soft", "hard"]

# Periodic no-op so a grabbed, event-starved loop keeps handing control back
# to Python, letting SIGTERM/SIGINT be serviced promptly.
# Tk's attributes() takes the value positionally, so a bare `True` here
# trips the boolean-positional lint. Naming it satisfies both that rule
# and the type stubs, which have no keyword overload.
_TOPMOST_ON = True

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
            typeable, WM-escapable. "hard" = overrideredirect + global grab +
            VT-disable (the production lock for all three apps).
        overrideredirect: Force a WM-unmanaged window. None = derive from mode.
            Note that per-output placement *requires* this: a window manager
            rewrites a managed window's geometry wholesale.
        grab: Input grab strategy. None = derive from mode.
        disable_vt: Disable Ctrl+Alt+Fn VT switching. None = derive from mode.
        grab_retry_ms: Retry interval in ms for a "global" grab that initially
            fails. 0 means "try once, then fall back to a local grab". Left
            unset (None), a "global" grab retries forever every 200ms.
        grab_log_every: Log a warning every N failed retry-forever attempts.
        app_name: This app's name, used in arbitration logs so a blocked app
            can say who is actually holding the screen.
        rank: Arbitration priority; higher wins. See the ``RANK_*`` constants
            in :mod:`gatelock._arbiter`.
        recovery_tick_ms: Interval of the full re-assertion pass.
        detect_drain_ms: Interval of the cheap "did anything change?" drain.
        bg: Background color for the lock surfaces.
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
    """

    mode: LockMode = "hard"
    overrideredirect: bool | None = None
    grab: GrabKind | None = None
    disable_vt: bool | None = None
    grab_retry_ms: int | None = None
    grab_log_every: int = 25
    app_name: str = "gatelock"
    rank: int = RANK_SCREEN_LOCKER
    recovery_tick_ms: int = 1000
    detect_drain_ms: int = 100
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


class LockWindow:
    """Per-output lock surfaces, input grab, and exit-path lifecycle."""

    def __init__(
        self,
        root: tk.Tk,
        config: LockConfig,
        hooks: LockWindowHooks,
        *,
        arbiter: Arbiter | None = None,
    ) -> None:
        """Initialize the lock window wrapper.

        Args:
            root: The Tk root to configure and own the lifecycle of. It becomes
                the backdrop and the grab holder; per-output surfaces are its
                children.
            config: Declarative lock behavior for this instance.
            hooks: App-supplied callbacks for surfaces, focus, errors, teardown.
            arbiter: The arbiter whose claim this lock is arming under. Used to
                name the real holder when a grab is blocked, and released on
                close so the next app can arm.
        """
        self.root = root
        self._config = config
        self._hooks = hooks
        self._arbiter = arbiter
        self._vt_disabled = False
        self._closed = False
        self._focus_notified = False
        self._surfaces = SurfaceSet(root, config, hooks)
        self._enumerator = OutputEnumerator(root)
        self._detector = OutputChangeDetector(root)
        self._recovery = RecoveryLoop(
            root, config, self._surfaces, self._enumerator, self._detector
        )

    @property
    def surfaces(self) -> SurfaceSet:
        """The live surface set, for apps that need to fan work out over it."""
        return self._surfaces

    # -- window mechanics -----------------------------------------------------

    def setup(self) -> None:
        """Configure the backdrop and build a surface on every live output.

        Disables VT switching first: strengthening the lock must not wait on
        being able to draw anything. If no output is live, no surface is built
        and the lock stays armed and invisible until one appears.
        """
        if self._config.resolved_disable_vt():
            self._vt_disabled = disable_vt_switching()

        if needs_backdrop_root(self._config):
            # The root is a plain black backdrop spanning the whole X screen,
            # including any region a modeless output left behind. It holds the
            # grab (X will not grab for a window that is not viewable) and
            # never carries widgets.
            self.root.overrideredirect(boolean=self._config.resolved_overrideredirect())
            self._surfaces.update_backdrop()
        else:
            self.root.attributes("-topmost", _TOPMOST_ON)

        scan = self._enumerator.scan()
        delta = self._surfaces.apply(scan)
        if not scan.live:
            _logger.warning(
                "no live outputs at startup (source=%s); arming the lock with "
                "nothing displayed -- it will appear as soon as a monitor "
                "comes back",
                scan.source,
            )
        else:
            _logger.info(
                "lock armed on %d output(s): %s",
                len(scan.live),
                ", ".join(output.name for output in scan.live),
            )
        if delta.unverified:
            _logger.error(
                "outputs live but not covered at startup: %s",
                ", ".join(delta.unverified),
            )

    def grab_input(self) -> None:
        """Take the configured grab, then start watching for output changes."""
        self.root.update_idletasks()
        self.root.focus_force()
        grab = self._config.resolved_grab()
        if grab == "global":
            self._acquire_global_grab(attempt=1)
        elif grab == "local":
            with contextlib.suppress(tk.TclError):
                self.root.grab_set()
        self._detector.start()
        self._recovery.start()
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
                self._log_grab_blocked(attempt)
            self.root.after(
                effective_retry_ms,
                lambda: self._acquire_global_grab(attempt=attempt + 1),
            )
            return
        with contextlib.suppress(tk.TclError):
            self.root.focus_force()
            self._notify_focus_ready()

    def _log_grab_blocked(self, attempt: int) -> None:
        """Say who is actually holding the grab, rather than guessing.

        v0.1.1 always blamed "a fullscreen game". On 2026-07-25 the holder was
        the other locker, and that guess sent the diagnosis in the wrong
        direction for the length of the outage.
        """
        holder = self._arbiter.describe_holder() if self._arbiter else None
        if holder is None:
            _logger.warning(
                "global grab still blocked after %d attempts; no gatelock app "
                "holds it -- likely another X client (e.g. a fullscreen game)",
                attempt,
            )
            return
        _logger.warning(
            "global grab still blocked after %d attempts; held by gatelock app "
            "%r (rank %d, pid %d) since %s",
            attempt,
            holder.app,
            holder.rank,
            holder.pid,
            holder.started,
        )

    def _notify_focus_ready(self) -> None:
        """Tell the app it can focus its first input widget now.

        Guarded rather than de-duplicated at the call sites: both timings are
        load-bearing. The 100ms ``after`` covers a grab that succeeds
        immediately, and the call from :meth:`_acquire_global_grab` covers one
        that only succeeds after seconds of retrying.
        """
        if self._focus_notified:
            return
        self._focus_notified = True
        with contextlib.suppress(tk.TclError):
            index = self._surfaces.preferred_focus_index()
            self._hooks.on_focus_ready(self._surfaces.focus_surface(index))

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
        """Run app teardown, release the screen, destroy every window.

        Idempotent -- safe to call directly (normal dismiss) and again from
        :meth:`run`'s ``finally`` (crash/signal exit) without double-running
        app teardown.

        Releasing the arbiter here is what makes a *clean* handoff work: the
        morning routine runs the alarm and then the workout locker as
        sequential subprocesses, and a claim left behind would make the second
        one stand down against an app that had already exited.
        """
        if self._closed:
            return
        self._closed = True
        self._recovery.stop()
        self._detector.stop()
        self._hooks.on_close()
        self._restore_vt()
        if self._arbiter is not None:
            self._arbiter.release()
        self._enumerator.close()
        with contextlib.suppress(tk.TclError):
            self._surfaces.destroy_all()
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
