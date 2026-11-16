# Copyright (c) 2026 Krzysztof Rudnicki. MIT License.
"""The worker heartbeat."""

from __future__ import annotations

import asyncio

import pytest

from rtdb_relay.presence import beat_forever, node
from rtdb_relay.tests._fake_rtdb import ROOT, FakeRtdb


def test_beats_until_cancelled() -> None:
    fake = FakeRtdb()
    sleeps: list[float] = []

    async def go() -> None:
        db = fake.rtdb()

        async def sleep(s: float) -> None:
            sleeps.append(s)
            if len(sleeps) == 2:
                raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await beat_forever(db, "pc", "1.0", sleep)
        await db.aclose()

    asyncio.run(go())
    stored = fake.get(f"{ROOT}/presence/workers/pc")
    assert stored["beat"] == fake.now_ms
    assert stored["version"] == "1.0"
    assert sleeps == [30.0, 30.0]
    assert set(node("v")) == {"beat", "host", "version"}
