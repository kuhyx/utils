"""RTDB streaming: Server-Sent Events, reconnected until told to stop.

tutor's ``sse.py`` on threads. Each (re)connect starts with a ``put`` of the
whole node at ``/``, so a consumer that applies ``put``/``patch`` events is
correct again after any drop. ``auth_revoked`` (the id token expired)
reconnects at once with a fresh token; a network error, an HTTP error, a bad
payload or a connection that closes before saying anything backs off 1-30 s;
``cancel`` (the rules now refuse the path) is fatal. `stop` is checked
between events: a quiet stream notices it at its next keep-alive (<= 30 s).
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import json
import logging
from typing import TYPE_CHECKING, Final, Protocol

from leetcode_coach.relay.rtdb import RtdbError, parse

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterator
    import threading

__all__ = ["BACKOFF_S", "Event", "StreamCancelledError", "listen", "parse"]

BACKOFF_S: Final = (1.0, 2.0, 5.0, 10.0, 30.0)
_DATA_EVENTS: Final = frozenset({"put", "patch"})
_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    """One ``put``/``patch`` event: where it applies and the new data."""

    kind: str
    path: str
    data: object


class StreamCancelledError(RtdbError):
    """RTDB cancelled the stream (rules refuse the path): not retried."""


class Streams(Protocol):
    """What `listen` needs of `rtdb.Rtdb`."""

    def stream(self, path: str) -> Generator[tuple[str, str]]:
        """The raw blocks of one connection."""


@dataclass
class _Health:
    """Whether a connection proved itself (an event, or a clean revocation)."""

    good: bool = False


def _event(kind: str, raw: str) -> Event:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        msg = f"a {kind} payload is not an object"
        raise TypeError(msg)
    return Event(kind, str(payload.get("path", "/")), payload.get("data"))


def _connection(
    rtdb: Streams, path: str, stop: threading.Event, health: _Health
) -> Iterator[Event]:
    """Events of a single connection; returns on EOF, revocation or `stop`."""
    with closing(rtdb.stream(path)) as blocks:
        for kind, raw in blocks:
            if kind in _DATA_EVENTS:
                event = _event(kind, raw)
                health.good = True
                yield event
                if stop.is_set():
                    return
            elif kind == "auth_revoked":
                _logger.info("stream %s: token expired, reconnecting", path)
                health.good = True
                return
            elif kind == "cancel":
                msg = f"stream {path} cancelled by the server"
                raise StreamCancelledError(msg)


def listen(
    rtdb: Streams,
    path: str,
    stop: threading.Event,
    sleep: Callable[[float], object] | None = None,
) -> Iterator[Event]:
    """Every event at ``path`` across reconnects, until `stop` is set."""
    pause = stop.wait if sleep is None else sleep
    failures = 0
    while not stop.is_set():
        health = _Health()
        reason = "closed before any event"
        try:
            yield from _connection(rtdb, path, stop, health)
        except StreamCancelledError:
            raise
        except (RtdbError, ValueError, TypeError) as err:
            # ValueError: a payload that is not JSON; TypeError: not an object.
            reason = str(err)
            _logger.warning("stream %s dropped: %s", path, reason)
        else:
            if health.good:
                failures = 0
                continue
        if health.good:
            failures = 0
        if stop.is_set():
            return
        delay = BACKOFF_S[min(failures, len(BACKOFF_S) - 1)]
        failures += 1
        _logger.warning("stream %s: %s; retry in %.0fs", path, reason, delay)
        pause(delay)
