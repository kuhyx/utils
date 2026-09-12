# Copyright (c) 2026 Krzysztof Rudnicki
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
import logging
import signal
import tkinter as tk
from typing import TYPE_CHECKING

from gatelock import _arming, _preempt
from gatelock._detect import OutputChangeDetector
from gatelock._outputs import OutputEnumerator
from gatelock._recovery import RecoveryCollaborators, RecoveryLoop
from gatelock._surfaces import SurfaceSet
from gatelock._vt import restore_vt_switching

if TYPE_CHECKING:
    from types import FrameType

    from gatelock._arbiter import Arbiter
    from gatelock._config import LockConfig
    from gatelock._hooks import LockWindowHooks

_logger = logging.getLogger(__name__)

# Periodic no-op so a grabbed, event-starved loop keeps handing control back
# to Python, letting SIGTERM/SIGINT be serviced promptly.
_KEEPALIVE_MS = 250


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
        self._preempted_pids: set[int] = set()
        surfaces = SurfaceSet(root, config, hooks)
        enumerator = OutputEnumerator(root)
        detector = OutputChangeDetector(root)
        recovery = RecoveryLoop(
            root,
            RecoveryCollaborators(
                config=config,
                surfaces=surfaces,
                enumerator=enumerator,
                detector=detector,
                hooks=hooks,
            ),
        )
        # The arming bundle is also where the window reaches its
        # collaborators afterwards; it is the one owner of those four.
        self._arming = _arming.ArmingCollaborators(
            config=config,
            surfaces=surfaces,
            enumerator=enumerator,
            detector=detector,
            recovery=recovery,
            notify_focus_ready=self._notify_focus_ready,
            log_grab_blocked=self._log_grab_blocked,
        )

    @property
    def surfaces(self) -> SurfaceSet:
        """The live surface set, for apps that need to fan work out over it."""
        return self._arming.surfaces

    @property
    def recovery(self) -> RecoveryLoop:
        """The re-assertion loop, for an app that suspends the lock.

        Releasing the grab while this runs is pointless: it re-takes the grab
        within a tick. An app that hands the screen to something else
        (leetcode-guard's study mode) stops this and :attr:`detector` first,
        and starts both again when it re-arms.
        """
        return self._arming.recovery

    @property
    def detector(self) -> OutputChangeDetector:
        """The output-change watcher; see :attr:`recovery` for when to stop it."""
        return self._arming.detector

    # -- window mechanics -----------------------------------------------------

    def setup(self) -> None:
        """Configure the backdrop and build a surface on every live output.

        Delegates to :func:`gatelock._arming.setup`.
        """
        self._vt_disabled = _arming.setup(self.root, self._arming)

    def grab_input(self) -> None:
        """Take the configured grab, then start watching for output changes.

        Delegates to :func:`gatelock._arming.grab_input`.
        """
        _arming.grab_input(self.root, self._arming)

    def _acquire_global_grab(self, *, attempt: int) -> None:
        """Acquire the global grab, retrying per ``grab_retry_ms``.

        Delegates to :func:`gatelock._arming.acquire_global_grab`.
        """
        _arming.acquire_global_grab(self.root, self._arming, attempt=attempt)

    def _log_grab_blocked(self, attempt: int) -> None:
        """Log who holds the grab, and stand a weaker holder down.

        Delegates to :mod:`gatelock._preempt`; see there for the policy and
        why a stronger holder is left alone.
        """
        _preempt.log_grab_blocked(
            attempt,
            arbiter=self._arbiter,
            config=self._config,
            preempted_pids=self._preempted_pids,
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
            index = self._arming.surfaces.preferred_focus_index()
            self._hooks.on_focus_ready(self._arming.surfaces.focus_surface(index))

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
        self._arming.recovery.stop()
        self._arming.detector.stop()
        self._hooks.on_close()
        self._restore_vt()
        if self._arbiter is not None:
            self._arbiter.release()
        self._arming.enumerator.close()
        with contextlib.suppress(tk.TclError):
            self._arming.surfaces.destroy_all()
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
