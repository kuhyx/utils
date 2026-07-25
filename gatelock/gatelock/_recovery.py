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
    from gatelock._window import LockConfig

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


class RecoveryLoop:
    """Re-asserts the lock's coverage on a timer and on change events."""

    def __init__(
        self,
        root: tk.Misc,
        config: LockConfig,
        surfaces: SurfaceSet,
        enumerator: OutputEnumerator,
        detector: OutputChangeDetector,
    ) -> None:
        """Wire the loop to the pieces it re-asserts over."""
        self._root = root
        self._config = config
        self._surfaces = surfaces
        self._enumerator = enumerator
        self._detector = detector
        self._running = False
        self._ticks = 0
        self._drain_job: str | None = None
        self._verify_job: str | None = None

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
        if self._detector.take_pending():
            _logger.debug("output-change signal received; re-asserting the lock")
            self.tick()
        self._schedule_drain()

    def _verify(self) -> None:
        """Run a full tick unconditionally."""
        self.tick()
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
        if self._holds_grab():
            return False
        with contextlib.suppress(tk.TclError):
            self._root.grab_set_global()
            _logger.warning("global grab had been lost; re-acquired it")
            return True
        return False

    def _holds_grab(self) -> bool:
        """Whether our root still owns the grab."""
        try:
            current = self._root.grab_current()
        except tk.TclError:
            return False
        return current is self._root

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
