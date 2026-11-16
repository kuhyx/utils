# Copyright (c) 2026 Krzysztof Rudnicki. MIT License.
"""SSE parsing, reconnects (drop, auth_revoked, errors), cancel; the mirror."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from rtdb_relay import mirror, sse
from rtdb_relay.sse import Event, StreamCancelledError, parse
from rtdb_relay.tests._fake_rtdb import FakeRtdb

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def test_parse_block() -> None:
    assert parse(["event: put", 'data: {"a":1}', "id: 3"]) == ("put", '{"a":1}')
    assert parse(["data: x", "data: y"]) == ("message", "x\ny")


async def _take(agen: AsyncIterator[Event], n: int) -> list[Event]:
    out = []
    async for event in agen:
        out.append(event)
        if len(out) == n:
            break
    return out


def test_listen_snapshot_then_writes_and_reconnects() -> None:
    fake = FakeRtdb()
    fake.set("tutor/v1-e2e/requests/a", {"req": 1})
    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    async def go() -> list[Event]:
        db = fake.rtdb()
        stream = sse.listen(db, "requests", sleep=sleep)
        got = await _take(stream, 1)
        await db.put("requests/b/req", 2)
        got += await _take(stream, 1)
        fake.push("event: keep-alive\ndata: null\n\n")
        fake.push("event: auth_revoked\ndata: credential is no longer valid\n\n")
        got += await _take(stream, 1)  # reconnected: snapshot again
        fake.push(None)  # server closes: reconnect at once
        got += await _take(stream, 1)
        fake.raise_on.add(("GET", "/requests"))
        fake.push(None)

        async def heal(delay: float) -> None:
            sleeps.append(delay)
            fake.raise_on.clear()

        stream2 = sse.listen(db, "requests", sleep=heal)
        fake.raise_on.add(("GET", "/requests"))
        got += await _take(stream2, 1)
        fake.push('event: put\ndata: {"path": "/x", "data": 1}\n\n')
        got += await _take(stream2, 1)
        await stream.aclose()
        await stream2.aclose()
        await db.aclose()
        return got

    got = asyncio.run(go())
    assert got[0] == Event("put", "/", {"a": {"req": 1}})
    assert got[1] == Event("put", "/b/req", 2)
    assert got[2].path == "/"
    assert got[2].data == {"a": {"req": 1}, "b": {"req": 2}}
    assert got[3].path == "/"
    assert got[4].path == "/"
    assert got[5] == Event("put", "/x", 1)
    assert sleeps == [1.0]


def test_listen_backoff_grows_and_bad_json_retries() -> None:
    fake = FakeRtdb()
    fake.raise_on.add(("GET", "/n"))
    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)
        if len(sleeps) == 6:
            fake.raise_on.clear()

    async def go() -> list[Event]:
        db = fake.rtdb()
        stream = sse.listen(db, "n", sleep=sleep)
        got = await _take(stream, 1)
        fake.push("event: patch\ndata: {not json\n\n")
        got += await _take(stream, 1)  # dropped, backed off, reconnected
        await stream.aclose()
        await db.aclose()
        return got

    got = asyncio.run(go())
    assert [e.path for e in got] == ["/", "/"]
    assert sleeps == [1.0, 2.0, 5.0, 10.0, 30.0, 30.0, 1.0]


def test_cancel_is_fatal() -> None:
    fake = FakeRtdb()

    async def go() -> None:
        db = fake.rtdb()
        stream = sse.listen(db, "c")
        await _take(stream, 1)
        fake.push("event: cancel\ndata: permission denied\n\n")
        with pytest.raises(StreamCancelledError):
            await _take(stream, 1)
        await db.aclose()

    asyncio.run(go())


def test_mirror_applies_put_and_patch() -> None:
    tree = mirror.apply({}, Event("put", "/", {"a": {"req": 1}}))
    tree = mirror.apply(tree, Event("put", "/b/req", 2))
    tree = mirror.apply(tree, Event("patch", "/a", {"claim": {"x": 1}, "req": None}))
    assert tree == {"a": {"claim": {"x": 1}}, "b": {"req": 2}}
    tree = mirror.apply(tree, Event("put", "/a/claim/x", None))
    assert tree == {"b": {"req": 2}}
    tree = mirror.apply(tree, Event("put", "/b/req/deep", 3))  # replaces a leaf
    assert tree == {"b": {"req": {"deep": 3}}}
    tree = mirror.apply(tree, Event("patch", "/", {"c/d": 4}))
    assert tree["c"] == {"d": 4}
    tree = mirror.apply(tree, Event("patch", "/", None))
    assert mirror.apply(tree, Event("put", "/", None)) == {}
    assert mirror.first_key("/a/b") == "a"
    assert mirror.first_key("/") is None


def test_blank_lines_without_a_block_are_skipped() -> None:
    async def lines() -> AsyncIterator[str]:
        for line in ("", "event: put", "data: {}", "", ""):
            yield line

    async def go() -> list[tuple[str, str]]:
        return [b async for b in sse._blocks(lines())]

    assert asyncio.run(go()) == [("put", "{}")]
