"""The coach's model chain once Claude is out: OmniRoute ``free-best``, then Ollama.

kuhy 2026-11-27: on a Claude usage limit the REPL, the relay and the graders go
on with the free models through OmniRoute, and with the local Ollama model only
when the gateway is down, empty or the prompt too long for it. Each rung is a
``chat(messages, timeout=...) -> LocalReply``; any transport error (``OSError``
covers ``URLError``, refused connections, timeouts and
:class:`~leetcode_coach.omniroute_backend.GatewayError`) or a context overflow
moves on to the next. The last rung's error propagates, so the callers' own
"model is down" handling stays as it was.
"""

from __future__ import annotations

from collections.abc import Callable
import logging
import time
from typing import TYPE_CHECKING

from leetcode_coach import local_backend, omniroute_backend

if TYPE_CHECKING:
    from collections.abc import Sequence

_LOG = logging.getLogger(__name__)


Rung = Callable[..., local_backend.LocalReply]
"""One model of the chain: ``rung(messages, timeout=seconds) -> LocalReply``."""


def chat(
    messages: list[dict[str, str]],
    *,
    timeout: float = omniroute_backend.REQUEST_TIMEOUT_S,
    rungs: Sequence[Rung] | None = None,
    on_fallback: Callable[[str], None] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> local_backend.LocalReply:
    """The first rung's reply that comes back; ``on_fallback`` hears each skip.

    ``timeout`` bounds the whole chain, not each rung: a rung gets what the
    ones before it left, so the relay's per-request cap still holds.

    Raises:
        OSError: every rung's transport failed (the last error).
        ContextOverflowError: the last rung could not fit the prompt either.
    """
    # Looked up per call, so a test that swaps a backend's `chat` is honoured.
    chain = (
        (omniroute_backend.chat, local_backend.chat) if rungs is None else tuple(rungs)
    )
    deadline = clock() + timeout
    for rung in chain[:-1]:
        try:
            return rung(messages, timeout=_left(deadline, clock))
        except (OSError, local_backend.ContextOverflowError) as exc:
            why = f"omniroute failed ({type(exc).__name__}: {exc}); next model"
            _LOG.warning("%s", why)
            if on_fallback is not None:
                on_fallback(why)
    return chain[-1](messages, timeout=_left(deadline, clock))


def _left(deadline: float, clock: Callable[[], float]) -> float:
    """Seconds until ``deadline``; a ``TimeoutError`` when under one is left."""
    left = deadline - clock()
    if left < 1.0:
        msg = "no time left for another model"
        raise TimeoutError(msg)
    return left
