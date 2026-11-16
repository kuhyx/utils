# Copyright (c) 2026 Krzysztof Rudnicki
"""An open lock window notices a credit that landed while it was up.

Born in screen-locker (2026-11-16): the window opened at 07:55, a workout was
credited at 07:59 by a separate daemon, and the open window never noticed --
the startup ladder reads the log once. This is the shared form of that fix, so
every gate that earns its way down can take itself down the same way.

Event-driven on the Tk ``after`` loop, no thread, no dependency. Each poll is
one ``stat`` per watched file; the owner's "is it done today?" verdict (which
may parse and HMAC-check the log) runs only when a file's (mtime, size, inode)
moved, plus once on the first poll. The credit itself was already written by
whoever earned it, so ``on_credit`` writes nothing: it only takes the window
down through the owner's normal close path.

Failure modes, chosen out loud: **fail closed**. A file that cannot be stat'ed
or a verdict that raises is logged and retried at the next poll; the lock stays
up. Only a verdict of True ever lifts it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path
    from tkinter import Misc

__all__ = ["CREDIT_POLL_MS", "watch_credit"]

_logger: Final = logging.getLogger(__name__)

# Well inside the 10 s an open window may take to notice a credit.
CREDIT_POLL_MS: Final = 3_000

_Signature = tuple[tuple[int, ...], ...]
# Never equals a real signature, so the first poll always asks.
_UNSEEN: Final[_Signature] = ((-1,),)
_ABSENT: Final[tuple[int, ...]] = ()
# What a verdict or close path may raise on a bad read; anything else is a bug
# and should surface, not be swallowed by a watcher.
_CHECK_ERRORS: Final = (OSError, ValueError, TypeError, LookupError, RuntimeError)


def _signature(paths: Sequence[Path], poll_ms: int) -> _Signature | None:
    """(mtime_ns, size, inode) per path: ``()`` if absent, None if unreadable."""
    parts: list[tuple[int, ...]] = []
    for path in paths:
        try:
            stat = path.stat()
        except FileNotFoundError:
            # A file nobody has written yet is normal, not a fault.
            parts.append(_ABSENT)
            continue
        except OSError as exc:
            _logger.warning(
                "Could not stat %s while the lock is up (%s) -- keeping the "
                "lock and trying again in %d s",
                path,
                exc,
                poll_ms // 1000,
            )
            return None
        parts.append((stat.st_mtime_ns, stat.st_size, stat.st_ino))
    return tuple(parts)


def watch_credit(
    root: Misc,
    paths: Sequence[Path],
    is_done: Callable[[], bool],
    on_credit: Callable[[], None],
    poll_ms: int = CREDIT_POLL_MS,
) -> None:
    """Hand a credit that landed while the window is up to ``on_credit``.

    Args:
        root: The Tk root whose ``after`` loop drives the polling.
        paths: Files whose change can mean a credit landed (the log the owner
            reads). Absent files are fine; they count as "not there yet".
        is_done: The owner's own "is today satisfied?" check. Called on the
            first poll and whenever a watched file changed, never otherwise.
        on_credit: Called once when ``is_done`` returns True; should close the
            window through its normal path. The watch stops re-arming then.
        poll_ms: Interval between polls.

    Raises:
        ValueError: ``paths`` is empty or ``poll_ms`` is not positive.

    An ``is_done`` or ``on_credit`` that raises an OSError, ValueError,
    TypeError, LookupError or RuntimeError is logged and retried at the
    next poll: one bad read must not end the only thing watching.
    """
    if not paths:
        msg = "watch_credit needs at least one path to watch (paths is empty)"
        raise ValueError(msg)
    if poll_ms <= 0:
        msg = f"poll_ms must be positive, got {poll_ms}"
        raise ValueError(msg)
    seen = _UNSEEN

    def _tick() -> None:
        nonlocal seen
        sig = _signature(paths, poll_ms)
        if sig is not None and sig != seen:
            seen = sig
            try:
                if is_done():
                    on_credit()
                    return
            except _CHECK_ERRORS:
                _logger.exception(
                    "Credit check failed while the lock is up -- keeping the "
                    "lock and trying again in %d s",
                    poll_ms // 1000,
                )
                seen = _UNSEEN
        root.after(poll_ms, _tick)

    root.after(poll_ms, _tick)
