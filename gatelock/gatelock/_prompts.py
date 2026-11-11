# Copyright (c) 2026 Krzysztof Rudnicki
"""Stepping aside for a system credential prompt that holds the X grab.

Incident 2026-11-11: the GNOME Keyring prompt (``gcr-prompter``) was mapped and
holding the X keyboard+pointer grab when a lock armed. The lock's
override-redirect windows covered it, so the grab could never be taken, every
click went to a window nobody could see, and the lock's own UI was dead.

The policy (approved by the user): when the global grab has been unobtainable
for more than :data:`YIELD_AFTER_S` AND a mapped window on the allowlist
(:data:`gatelock._prompt_names.SYSTEM_PROMPT_CLASSES`) is on screen, raise that
prompt above the lock and stop the lock's own periodic re-raise from covering
it again, for as long as the prompt stays mapped. Everything else stays as it
was: the lock is still mapped everywhere, VT switching stays disabled and the
grab is still retried every tick. Once the grab is taken the lock stacks on top
again. Anything not on the allowlist -- a fullscreen game -- is never yielded
to.

Known limitation of an allowlist keyed on WM_CLASS: a window that merely
*claims* one of those classes while holding a grab would be raised too.

This module is the policy and the clock. All X access is in
:mod:`gatelock._prompts_x`. It is deliberately NOT named ``_recovery_*``: the
recovery family is statically checked to contain no release call, and keeping
the X plumbing out of it keeps that check meaningful.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Final, Protocol

from gatelock._grabprobe import GrabProbe
from gatelock._prompts_x import XPromptProbe

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock._prompt_names import PromptWindow

_logger = logging.getLogger(__name__)

YIELD_AFTER_S: Final = 2.0
"""How long the grab must stay unobtainable before looking for a prompt."""


class PromptProbe(Protocol):
    """What the policy needs from the X side."""

    def raise_prompts(self) -> tuple[PromptWindow, ...]:
        """Raise every mapped allowlisted prompt; return those it raised."""


class PromptYield:
    """Times a blocked grab and decides whether to raise a prompt over the lock."""

    def __init__(
        self,
        probe: PromptProbe | None = None,
        *,
        grab_probe: GrabProbe | None = None,
        clock: Callable[[], float] = time.monotonic,
        after_s: float = YIELD_AFTER_S,
    ) -> None:
        """Build the policy; nothing is blocked yet.

        Args:
            probe: Finds and raises prompts. Defaults to the python-xlib one.
            grab_probe: Asks X whether the grab is free. Defaults to the real one.
            clock: Monotonic seconds; injected by tests.
            after_s: Seconds the grab must stay blocked before yielding.
        """
        self._probe: PromptProbe = probe if probe is not None else XPromptProbe()
        self._grab_probe = grab_probe if grab_probe is not None else GrabProbe()
        self._clock = clock
        self._after_s = after_s
        self._blocked_since: float | None = None
        self._reason = ""
        self._prompts: tuple[PromptWindow, ...] = ()

    @property
    def last_reason(self) -> str:
        """Tk's message for the most recent failed grab (empty if none yet)."""
        return self._reason

    @property
    def yielding(self) -> bool:
        """Whether a prompt is being yielded to right now."""
        return bool(self._prompts)

    @property
    def prompt_names(self) -> tuple[str, ...]:
        """WM_CLASS instances of the prompts currently yielded to."""
        return tuple(prompt.name for prompt in self._prompts)

    def check_grab(self) -> None:
        """Raise ``tk.TclError`` if the grab is known to be held elsewhere.

        Call before every ``grab_set_global()``: Tk blocks its whole event
        loop for ~1 s on each failed attempt, so a doomed one is skipped.
        """
        self._grab_probe.check()

    def grab_blocked(self, reason: str) -> None:
        """Record a failed grab; the first failure starts the clock.

        Args:
            reason: Tk's error text ("another application has grab", ...).
        """
        self._reason = reason
        if self._blocked_since is None:
            self._blocked_since = self._clock()

    def grab_held(self) -> bool:
        """Record that the grab is ours; end any yield.

        Returns:
            True when a yield was in progress, so the caller must lift the
            lock over whatever it had stepped aside for.
        """
        self._blocked_since = None
        was_yielding = self.yielding
        self._prompts = ()
        if was_yielding:
            _logger.warning("global grab taken; the lock stacks on top again")
        return was_yielding

    def settle(self) -> None:
        """Re-decide, and re-raise the prompt. Call LAST in a recovery tick.

        Last, so that nothing the tick lifted can end up above the prompt.
        """
        since = self._blocked_since
        if since is None or self._clock() - since < self._after_s:
            return
        previous = self.prompt_names
        self._prompts = self._probe.raise_prompts()
        if self.prompt_names == previous:
            return
        if self._prompts:
            _logger.warning(
                "global grab blocked for %.1fs (%s) and system prompt %s is on "
                "screen; raising it above the lock so it can be answered. The "
                "lock stays up, VT stays disabled, the grab keeps being retried",
                self._clock() - since,
                self._reason,
                ", ".join(self.prompt_names),
            )
        else:
            _logger.info("system prompt %s is gone; lock on top", ", ".join(previous))
