# Copyright (c) 2026 Krzysztof Rudnicki. MIT License.
"""RTDB streaming: Server-Sent Events, reconnected forever.

Each (re)connect starts with a ``put`` of the whole node at path ``/``, so a
consumer that mirrors ``put``/``patch`` events (``mirror.apply``) is always
correct after a drop. ``auth_revoked`` (the id token expired) reconnects at
once with a fresh token; network errors back off; ``cancel`` (the rules now
refuse the path) is fatal.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
from typing import TYPE_CHECKING, Any, Final

from rtdb_relay.rtdb import RtdbError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable

    from rtdb_relay.rtdb import Rtdb

BACKOFF_S: Final = (1.0, 2.0, 5.0, 10.0, 30.0)
_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    """One ``put``/``patch`` event: where it applies and the new data."""

    kind: str
    path: str
    data: Any


class StreamCancelledError(RtdbError):
    """RTDB cancelled the stream (rules refuse the path): not retried."""


def parse(lines: list[str]) -> tuple[str, str]:
    """``(event, data)`` of one SSE block (its lines, blank line excluded)."""
    event, data = "message", []
    for line in lines:
        field, _, value = line.partition(":")
        value = value.removeprefix(" ")
        if field == "event":
            event = value
        elif field == "data":
            data.append(value)
    return event, "\n".join(data)


async def _blocks(source: AsyncIterator[str]) -> AsyncIterator[tuple[str, str]]:
    block: list[str] = []
    async for line in source:
        if line:
            block.append(line)
        elif block:
            yield parse(block)
            block = []


def opened(rtdb: Rtdb, path: str, event: Event) -> Event:
    """``event`` with its sealed units opened (``path``: the listened node).

    A ``put``/``patch`` never lands below a unit: units are written whole.
    """
    where = f"{path.strip('/')}/{event.path.strip('/')}".strip("/")
    if event.kind == "put":
        return Event(event.kind, event.path, rtdb.opened(where, event.data))
    data = event.data if isinstance(event.data, dict) else {}
    body = {k: rtdb.opened(f"{where}/{k}", v) for k, v in data.items()}
    return Event(event.kind, event.path, body)


async def _one_connection(
    rtdb: Rtdb, path: str, params: dict[str, str] | None
) -> AsyncIterator[Event]:
    """Events of a single connection; returns on ``auth_revoked`` or EOF."""
    async for kind, raw in _blocks(rtdb.open_stream(path, params)):
        if kind in {"put", "patch"}:
            payload = json.loads(raw)
            event = Event(kind, str(payload.get("path", "/")), payload.get("data"))
            yield opened(rtdb, path, event)
        elif kind == "auth_revoked":
            _logger.info("stream %s: token expired, reconnecting", path)
            return
        elif kind == "cancel":
            msg = f"stream {path} cancelled by the server"
            raise StreamCancelledError(msg)


async def listen(
    rtdb: Rtdb,
    path: str,
    params: dict[str, str] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> AsyncGenerator[Event]:
    """Every event at ``path`` across reconnects; runs until cancelled."""
    failures = 0
    while True:
        try:
            async for event in _one_connection(rtdb, path, params):
                failures = 0
                yield event
        except StreamCancelledError:
            raise
        except (RtdbError, ValueError) as err:  # ValueError: a bad JSON payload
            delay = BACKOFF_S[min(failures, len(BACKOFF_S) - 1)]
            failures += 1
            _logger.warning("stream %s dropped (%s); retry in %.0fs", path, err, delay)
            await sleep(delay)
