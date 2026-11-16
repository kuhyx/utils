# Copyright (c) 2026 Krzysztof Rudnicki. MIT License.
"""The worker's heartbeat at ``presence/workers/{worker}``.

Clients judge the worker alive from when beats stop arriving (``beat`` is an
RTDB server timestamp, kept clear beside the sealed unit), never by
comparing it to their own clock.
"""

from __future__ import annotations

import asyncio
import socket
from typing import TYPE_CHECKING, Final

from rtdb_relay.rtdb import SERVER_TIME

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from rtdb_relay.rtdb import Rtdb

BEAT_S: Final = 30.0


def node(version: str) -> dict[str, object]:
    """One beat: server time, the host and the worker's build."""
    return {"beat": SERVER_TIME, "host": socket.gethostname(), "version": version}


async def beat_forever(
    rtdb: Rtdb,
    worker: str,
    version: str,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Write a beat every :data:`BEAT_S` until cancelled."""
    while True:
        await rtdb.put(f"presence/workers/{worker}", node(version))
        await sleep(BEAT_S)
