"""Keep the lock covering every live output, and never weaken it.

This loop is the watchdog the 2026-07-25 incident needed. A monitor that comes
back must show the lock immediately; a monitor that goes dark must not take the
lock's only escape UI with it.

Monotonicity
------------

Let ``C`` be the set of live outputs carrying a correctly-placed mapped
surface, ``G`` whether the global grab is held, and ``V`` whether VT switching
is disabled. Every tick satisfies:

    No transition decreases ``G`` or ``V``, and no transition removes an
    element of ``C`` whose output is still live.

The proof is by exhaustion over the operations a tick can perform: create a
surface, move one, remap one, raise one, destroy the surface of an output that
is *no longer live*, re-take the grab, re-disable VT switching. None of those
is a release. ``G`` and ``V`` are only ever set. ``C`` grows except when an
output stops being live -- and such an output is outside ``C``'s domain, so
``C`` restricted to live outputs never shrinks.

That property is *mechanical*, not aspirational. All structural change is
delegated to :mod:`gatelock._surfaces`, so this module contains none of
``grab_release``, ``restore_vt_switching``, ``close``, ``destroy``, ``quit`` or
``withdraw`` -- and a test parses this file to assert exactly that. Note the
asymmetry, which is the whole point: ``disable_vt_switching`` and
``grab_set_global`` *are* imported and called, because they strengthen. Only
their inverses are banned.

Consequence, deliberate: with zero live outputs the loop shows nothing and
keeps the grab. Pulling a cable is therefore not an escape.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
import logging
import tkinter as tk
from typing import TYPE_CHECKING

from gatelock._vt import disable_vt_switching

if TYPE_CHECKING:
    from gatelock._detect import OutputChangeDetector
    from gatelock._outputs import OutputEnumerator
    from gatelock._surfaces import SurfaceDelta, SurfaceSet
    from gatelock._window import LockConfig, LockWindowHooks

_logger = logging.getLogger(__name__)

_VT_REASSERT_EVERY = 30
"""Re-disable VT switching every N verify ticks, in case something reset it."""


@dataclass(frozen=True)
class RecoveryReport:
    """What one tick observed and corrected."""

    scan_ok: bool
    source: str
    live_outputs: tuple[str, ...] = ()
    delta: SurfaceDelta | None = None
    corrected: tuple[str, ...] = ()
    grab_reasserted: bool = False
    vt_reasserted: bool = False
    blind: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecoveryCollaborators:
    """The pieces one tick re-asserts over.

    Bundled to keep the loop's constructor at one object instead of a
    growing, unbounded arg list.
    """

    config: LockConfig
    surfaces: SurfaceSet
    enumerator: OutputEnumerator
    detector: OutputChangeDetector
    hooks: LockWindowHooks


class RecoveryLoop:
    """Re-asserts the lock's coverage on a timer and on change events."""

    def __init__(self, root: tk.Misc, collaborators: RecoveryCollaborators) -> None:
        """Wire the loop to the pieces it re-asserts over."""
        self._root = root
        self._config = collaborators.config
        self._surfaces = collaborators.surfaces
        self._enumerator = collaborators.enumerator
        self._detector = collaborators.detector
        self._hooks = collaborators.hooks
        self._running = False
        self._ticks = 0
        self._drain_job: str | None = None
        self._verify_job: str | None = None
        self._last_grab_warning: str | None = None

    @property
    def ticks(self) -> int:
        """How many full verify passes have run."""
        return self._ticks

    def start(self) -> None:
        """Begin both cadences: the cheap drain and the full verify."""
        self._running = True
        self._schedule_drain()
        self._schedule_verify()

    def stop(self) -> None:
        """Stop rescheduling. Cancels timers; touches no window state."""
        self._running = False
        for job in (self._drain_job, self._verify_job):
            if job is not None:
                with contextlib.suppress(tk.TclError):
                    self._root.after_cancel(job)
        self._drain_job = None
        self._verify_job = None

    def _schedule_drain(self) -> None:
        """Queue the next cheap drain tick."""
        if not self._running:
            return
        self._drain_job = self._root.after(self._config.detect_drain_ms, self._drain)

    def _schedule_verify(self) -> None:
        """Queue the next full verify tick."""
        if not self._running:
            return
        self._verify_job = self._root.after(self._config.recovery_tick_ms, self._verify)

    def _drain(self) -> None:
        """Run a full tick only if a push signal arrived. Cheap otherwise."""
        try:
            if self._detector.take_pending():
                _logger.debug("output-change signal received; re-asserting the lock")
                self.tick()
        # Same fail-open reasoning as _verify.
        except Exception:
            _logger.exception("drain tick raised; the lock loop keeps running")
        finally:
            self._schedule_drain()

    def _verify(self) -> None:
        """Run a full tick unconditionally.

        The reschedule is in ``finally`` because it is the only thing keeping
        the loop alive: a Tk ``after`` callback that raises just logs and
        returns, so scheduling *after* ``tick()`` meant one unexpected
        exception silently ended all re-assertion of coverage, grab and VT for
        the rest of the lock. Fail-open is the one outcome this module exists
        to prevent, so a broken tick must still leave the next one queued.
        """
        try:
            self.tick()
        except Exception:
            _logger.exception("verify tick raised; the lock loop keeps running")
        finally:
            self._schedule_verify()

    def tick(self) -> RecoveryReport:
        """Re-assert coverage, placement, grab and VT. Never weakens any of them.

        Returns:
            What this pass saw and corrected.
        """
        self._ticks += 1
        scan = self._enumerator.scan()

        if not scan.ok:
            # No information is not a reason to change anything. Keep every
            # surface, keep the grab, keep VT disabled, try again next tick.
            _logger.warning(
                "output enumeration failed; leaving the lock exactly as it is"
            )
            return RecoveryReport(scan_ok=False, source=scan.source)

        self._surfaces.update_backdrop()
        delta = self._surfaces.apply(scan)
        corrected = self._surfaces.enforce()
        grab_reasserted = self._reassert_grab()
        vt_reasserted = self._reassert_vt()
        if delta.created:
            self._reassert_focus()

        if delta.unverified:
            _logger.error(
                "these outputs are live but show no lock: %s -- the escape UI "
                "may be somewhere the user cannot see",
                ", ".join(delta.unverified),
            )
        if delta.changed:
            _logger.info(
                "surfaces changed (created=%s moved=%s removed=%s) from %s",
                delta.created,
                delta.moved,
                delta.removed,
                scan.source,
            )
        if not scan.live:
            _logger.warning(
                "no live outputs; showing nothing and STAYING LOCKED "
                "(grab and VT held) until one comes back"
            )

        return RecoveryReport(
            scan_ok=True,
            source=scan.source,
            live_outputs=tuple(output.name for output in scan.live),
            delta=delta,
            corrected=corrected,
            grab_reasserted=grab_reasserted,
            vt_reasserted=vt_reasserted,
            blind=delta.unverified,
        )

    def _reassert_grab(self) -> bool:
        """Re-take the global grab if we lost it. Never releases one.

        Returns:
            True if the grab had to be re-taken.
        """
        if self._config.resolved_grab() != "global":
            return False
        if self.holds_grab():
            return False
        with contextlib.suppress(tk.TclError):
            self._root.grab_set_global()
            _logger.warning("global grab had been lost; re-acquired it")
            return True
        return False

    def holds_grab(self) -> bool:
        """Whether the grab is held by a window this application owns.

        Deliberately *not* ``grab_current() is self._root``. Our own transient
        children take the grab for themselves: a posted Tk menu grabs the menu
        window, and the old identity test read that as "the grab was lost" and
        called ``grab_set_global()`` a second later, stealing it back off our
        own widget mid-interaction. That is what made the screen-locker sport
        selector unusable while locked on 2026-07-26. Any window we own still
        means the lock has the pointer and keyboard.

        ``grab_current`` resolves the name Tcl gives it against our own widget
        map, so anything that does not resolve -- a Tcl-created popdown such as
        a ``ttk.Combobox``'s, or a stale name -- raises ``KeyError`` and is NOT
        provably ours. That counts as lost and the grab is re-taken: fail
        closed, because this module exists to keep the lock, and losing a
        popdown beats believing we hold a grab we do not.

        Known limitation: a second ``tk.Tk()`` in the same process reports its
        root as ``"."`` too, which is indistinguishable from ours. The old
        identity test had exactly the same blind spot. ``_heat_skip``'s
        throwaway root is the only other one in screen-locker, and it is
        destroyed before the lock window exists.

        Public so an embedder (or a verification harness) can ask the same
        question the loop asks, rather than re-implementing it and drifting.
        """
        try:
            held = self._root.grab_current() is not None
        except KeyError as exc:
            self._warn_once(
                f"the grab is held by {exc.args[0]!r}, not one of our windows"
            )
            return False
        except tk.TclError:
            self._warn_once("could not read the current grab")
            return False
        if held:
            self._last_grab_warning = None
        return held

    def _reassert_focus(self) -> None:
        """Re-focus the preferred surface after any output came back live.

        ``LockWindow.grab_input()`` only focuses the entry once, on first
        acquisition (:meth:`LockWindow._notify_focus_ready` is one-shot). A
        surface that is rebuilt later -- an output going dark and returning,
        which a flaky monitor does routinely -- gets a brand new widget that
        nothing ever focuses. The lock keeps its grab, so no other window can
        take focus either: the entry renders correctly but is permanently
        keyboard-dead until the process restarts. Re-running the same
        focus_surface(preferred_focus_index()) call LockWindow makes on
        startup, here, whenever a surface was just (re)created, is what keeps
        that widget the actual Tk focus target.
        """
        with contextlib.suppress(tk.TclError):
            index = self._surfaces.preferred_focus_index()
            self._hooks.on_focus_ready(self._surfaces.focus_surface(index))

    def _warn_once(self, reason: str) -> None:
        """Warn about a lost grab, but only when the reason changes.

        These states can persist for the whole lock (a dark display, a popdown
        that keeps re-grabbing), and this runs once a second -- warning every
        tick would push a line per second into the journal for as long as it
        lasts. Silence is not the alternative: the first occurrence and every
        change of cause are still logged at WARNING.
        """
        if reason != self._last_grab_warning:
            _logger.warning("%s; treating it as lost and re-taking it", reason)
            self._last_grab_warning = reason

    def _reassert_vt(self) -> bool:
        """Periodically re-disable VT switching. Never re-enables it.

        Returns:
            True on ticks where the re-assert ran.
        """
        if not self._config.resolved_disable_vt():
            return False
        if self._ticks % _VT_REASSERT_EVERY:
            return False
        disable_vt_switching()
        return True
