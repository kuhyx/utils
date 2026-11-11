# Copyright (c) 2026 Krzysztof Rudnicki
"""A weaker armed lock steps back for a stronger one that appears.

Lockers that start together can still race: a weaker one that armed before a
stronger one had published stays armed, and the stronger then arms on top. Two
windows, the weaker one holding the grab, the visible one unclickable -- the
same symptom as the 2026-11-11 keyring incident. The startup grace in
:mod:`gatelock._queue` closes most of that window; this closes the rest (a
stronger locker that starts later, e.g. three seconds after).

While armed, the lock checks about once a second for a **live** claim that is
**strictly** higher ranked AND locks at least as firmly (grab kind and VT:
the arbiter's own rule that rank must never weaken a lock). Equal, lower,
weaker-locking and dead claims never trigger it. On a hit the lock suspends:
recovery and detector stop, the grab is released, surfaces and backdrop are
hidden and the holder lock is dropped. The **claim stays published**, so
lower-ranked apps keep queueing behind it. VT switching is left as it is: the
stronger lock disables it itself, and re-disabling is part of re-arming. It then
waits windowless -- the same turn logic as :func:`gatelock.wait_for_turn` --
and re-arms fully (VT, backdrop, surfaces, grab) once nothing qualifying is
live. It is the same process and lock: the app's state and callbacks are
untouched.

This module holds the library's ONLY ``grab_release`` and the only caller of
``SurfaceSet.set_visible(visible=False)``; a test pins both. It is kept out of
the ``_recovery*`` family, whose static invariant forbids release calls.
"""

from __future__ import annotations

import logging
import time
import tkinter as tk
from typing import TYPE_CHECKING

from gatelock._queue import QUEUE_DEADLINE_SECONDS, stronger_claims
from gatelock._vt import disable_vt_switching

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock._arbiter import Arbiter
    from gatelock._arming import ArmingCollaborators
    from gatelock._claims import Claim

_logger = logging.getLogger(__name__)


def outranking(arbiter: Arbiter) -> tuple[Claim, ...]:
    """Live claims that must make us step back: higher rank, at least as firm.

    ``stronger_claims`` proves liveness with ``flock`` (a dead owner's claim is
    reaped, never returned) and compares rank alone; the extra strength test is
    what stops a stronger-ranked but weaker-locking app from disarming us.
    """
    mine = arbiter.claim
    return tuple(c for c in stronger_claims(arbiter) if c.at_least_as_strong_as(mine))


def _attempt(action: Callable[[], None], what: str) -> None:
    """Run one Tk step; a failure is logged and the rest still happens."""
    try:
        action()
    except tk.TclError as exc:
        _logger.warning("step-back: %s failed (%s)", what, exc)


class StepBack:
    """Suspends an armed lock for a stronger one, and re-arms it afterwards."""

    def __init__(
        self,
        root: tk.Tk,
        arming: ArmingCollaborators,
        arbiter: Arbiter | None,
        rearm: Callable[[], None],
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Wire the controller; nothing is scheduled until :meth:`start`.

        Args:
            root: The Tk root (backdrop and grab holder).
            arming: The window's arming collaborators (surfaces, loop, ...).
            arbiter: This app's arbiter; None disables stepping back.
            rearm: Re-takes the grab and restarts the loops
                (``LockWindow.grab_input``).
            clock: Monotonic seconds; injected by tests.
        """
        self._root = root
        self._arming = arming
        self._arbiter = arbiter
        self._rearm = rearm
        self._clock = clock
        self._job: str | None = None
        self._since: float | None = None

    @property
    def suspended(self) -> bool:
        """Whether the lock is currently stepped back."""
        return self._since is not None

    def start(self) -> None:
        """Begin (or restart) the periodic check. Idempotent."""
        if self._arbiter is not None:
            self._schedule()

    def stop(self) -> None:
        """Cancel the periodic check."""
        if self._job is not None:
            _attempt(lambda: self._root.after_cancel(str(self._job)), "cancel")
            self._job = None

    def _schedule(self) -> None:
        """Queue the next check, replacing any pending one."""
        self.stop()
        self._job = self._root.after(self._arming.config.recovery_tick_ms, self._tick)

    def _tick(self) -> None:
        """One check; a raise must not end the checking."""
        self._job = None
        try:
            if self._since is None:
                self._maybe_suspend()
            else:
                self._maybe_resume(self._since)
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.exception("step-back check raised; checking continues")
        finally:
            self._schedule()

    def _maybe_suspend(self) -> None:
        """Step back if, and only if, a qualifying claim is live."""
        arbiter = self._arbiter
        # A stopped loop means the app took the lock down on purpose (study
        # mode); it is not ours to suspend or, later, to re-arm.
        if arbiter is None or not self._arming.recovery.running:
            return
        blockers = outranking(arbiter)
        if not blockers:
            return
        _logger.warning(
            "%s (rank %d) steps back: %s is live and outranks it; hiding, "
            "releasing the grab, waiting with no window",
            arbiter.claim.app,
            arbiter.claim.rank,
            ", ".join(f"{c.app} (rank {c.rank})" for c in blockers),
        )
        # First: if any step below raised, the next tick must still see us as
        # suspended and re-arm, never as armed with a half-stopped loop.
        self._since = self._clock()
        self._arming.recovery.stop()
        self._arming.detector.stop()
        _attempt(self._root.grab_release, "grab release")
        _attempt(lambda: self._arming.surfaces.set_visible(visible=False), "hide")
        _attempt(self._root.withdraw, "backdrop hide")
        arbiter.set_grab_held(held=False)
        arbiter.drop_holder()

    def _maybe_resume(self, since: float) -> None:
        """Re-arm once nothing qualifying is live (or the backstop is hit)."""
        arbiter = self._arbiter
        if arbiter is None:  # pragma: no cover - never suspended without one
            return
        waited = self._clock() - since
        if outranking(arbiter):
            if waited < QUEUE_DEADLINE_SECONDS:
                return
            _logger.error(
                "%s waited %.0fs stepped back and gave up -- re-arming anyway "
                "rather than leaving the machine unlocked",
                arbiter.claim.app,
                waited,
            )
        _logger.warning(
            "%s re-arms after %.0fs stepped back: nothing outranks it now",
            arbiter.claim.app,
            waited,
        )
        self._since = None
        arbiter.acquire_holder()
        if self._arming.config.resolved_disable_vt():
            disable_vt_switching()
        _attempt(self._root.deiconify, "backdrop show")
        _attempt(lambda: self._arming.surfaces.set_visible(visible=True), "show")
        self._rearm()
