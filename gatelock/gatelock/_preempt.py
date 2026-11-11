# Copyright (c) 2026 Krzysztof Rudnicki
"""Diagnosing and clearing a blocked global input grab.

Split out of :mod:`gatelock._window`, which owns the *acquisition* loop; this
module owns what happens when that loop keeps failing -- naming the holder in
the log, and standing a weaker one down.

Both are free functions rather than methods because neither touches the Tk
window: they need only the arbiter, the config knobs and the set of pids
already signalled. That keeps the retry path in one file and the arbitration
policy in another, and lets this half be tested without a display.
"""

from __future__ import annotations

import logging
import os
import signal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gatelock._arbiter import Arbiter
    from gatelock._claims import Claim
    from gatelock._config import LockConfig
    from gatelock._prompts import PromptYield

_logger = logging.getLogger(__name__)


def _foreign_holder(arbiter: Arbiter | None) -> Claim | None:
    """The gatelock app holding the screen, unless that app is this process.

    ``Arbiter.describe_holder`` answers "who owns the holder file", and when
    this process wrote it that is our own claim. Reporting it as the grab's
    holder made the lock blame itself (2026-11-11) and hid the real holder.
    """
    holder = arbiter.describe_holder() if arbiter else None
    if holder is None or arbiter is None:
        return None
    return None if holder.instance_id == arbiter.claim.instance_id else holder


def log_grab_blocked(
    attempt: int,
    *,
    arbiter: Arbiter | None,
    config: LockConfig,
    preempted_pids: set[int],
    prompt_yield: PromptYield | None = None,
) -> None:
    """Say who is actually holding the grab, rather than guessing.

    v0.1.1 always blamed "a fullscreen game". On 2026-07-25 the holder was
    the other locker, and that guess sent the diagnosis in the wrong
    direction for the length of the outage. On 2026-11-11 the lock blamed
    *itself* (its own holder file) while the holder was the GNOME Keyring
    prompt, so a holder that is this process counts as "no gatelock holder".

    A holder that outranks us is left alone entirely -- retrying is the
    correct behavior there, matching :func:`gatelock.wait_for_turn`'s own
    rule for an app that has not armed yet. A *weaker* holder is preempted
    by :func:`maybe_preempt`, once per pid, rather than left to block us for
    as long as it takes to finish on its own (diet_guard held the grab for
    ~3 minutes against a higher-ranked screen_locker on 2026-08-21).

    X cannot say which client holds a grab, so credential prompts seen on
    screen are named as *present*, not as the verdict.

    Args:
        attempt: 1-based attempt counter, reported in the log line.
        arbiter: This app's arbiter, or None when arbitration is disabled.
        config: The window's configuration, consulted for the preempt opt-in.
        preempted_pids: Pids already signalled; mutated by the preempt path.
        prompt_yield: The grab-block policy; supplies Tk's error text for the
            failed grab and the system prompts seen on screen.
    """
    reason = prompt_yield.last_reason if prompt_yield else ""
    prompts = prompt_yield.prompt_names if prompt_yield else ()
    cause = f" ({reason})" if reason else ""
    holder = _foreign_holder(arbiter)
    if holder is None:
        _logger.warning(
            "global grab still blocked after %d attempts%s; no other gatelock "
            "app holds it -- a non-gatelock X client does (e.g. a fullscreen "
            "game or a credential prompt)%s",
            attempt,
            cause,
            f"; system prompt on screen: {', '.join(prompts)}" if prompts else "",
        )
        return
    _logger.warning(
        "global grab still blocked after %d attempts%s; held by gatelock app "
        "%r (rank %d, pid %d) since %s",
        attempt,
        cause,
        holder.app,
        holder.rank,
        holder.pid,
        holder.started,
    )
    maybe_preempt(holder, arbiter=arbiter, config=config, preempted_pids=preempted_pids)


def maybe_preempt(
    holder: Claim,
    *,
    arbiter: Arbiter | None,
    config: LockConfig,
    preempted_pids: set[int],
) -> None:
    """SIGTERM a weaker holder once, so it stands down instead of blocking.

    SIGTERM (not SIGKILL): the holder's own signal handler
    (``LockWindow._install_signal_handlers``) raises ``SystemExit(0)``,
    which unwinds through its ``run()``'s ``finally`` into its own
    ``close()`` -- the identical teardown a clean dismiss gets (VT
    restored, arbiter claim released, app-specific ``on_close`` hook
    run), just triggered externally instead of by the user.

    Args:
        holder: The claim currently holding the grab.
        arbiter: This app's arbiter, or None when arbitration is disabled.
        config: The window's configuration; ``preempt_weaker_holder`` gates
            this entirely and defaults to off.
        preempted_pids: Pids already signalled, so each is signalled once.
    """
    if not config.grab.preempt_weaker_holder or arbiter is None:
        return
    if holder.rank >= arbiter.claim.rank:
        return
    if holder.pid in preempted_pids:
        return
    preempted_pids.add(holder.pid)
    _logger.warning(
        "preempting weaker holder %r (rank %d, pid %d) so rank %d can arm",
        holder.app,
        holder.rank,
        holder.pid,
        arbiter.claim.rank,
    )
    try:
        os.kill(holder.pid, signal.SIGTERM)
    except ProcessLookupError:
        _logger.info(
            "holder pid %d was already gone by the time we signalled it",
            holder.pid,
        )
    except OSError:
        _logger.exception("could not signal holder pid %d", holder.pid)
