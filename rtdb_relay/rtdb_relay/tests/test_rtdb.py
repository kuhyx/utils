# Copyright (c) 2026 Krzysztof Rudnicki. MIT License.
"""The RTDB REST client against the in-memory fake: ETags, 412, errors."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from rtdb_relay import rtdb as rtdb_mod
from rtdb_relay.rtdb import ConflictError, Rtdb, RtdbError
from rtdb_relay.tests._fake_rtdb import DB, ROOT, FakeRtdb, etag

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Coroutine


async def _drain(db: Rtdb) -> list[str]:
    return [line async for line in db.open_stream("s")]


def run(coro: Coroutine[Any, Any, None]) -> None:
    asyncio.run(coro)


def test_url_quotes_segments_and_root() -> None:
    fake = FakeRtdb(sealed=False)
    db = fake.rtdb()
    assert db.url("requests/a b") == f"{DB}/tutor/v1-e2e/requests/a%20b.json"
    assert db.url("/") == f"{DB}/tutor/v1-e2e.json"
    assert db.url("subjects/pojęcia-z-łodzi") == (
        f"{DB}/tutor/v1-e2e/subjects/poj%C4%99cia-z-%C5%82odzi.json"
    )
    run(db.aclose())


def test_put_get_patch_delete_round_trip() -> None:
    fake = FakeRtdb(now_ms=42, sealed=False)

    async def go() -> None:
        db = fake.rtdb()
        stored = await db.put("a/b", {"x": 1, "at": rtdb_mod.SERVER_TIME})
        assert stored == {"x": 1, "at": 42}
        await db.patch("a/b", {"y": 2, "x": None})
        assert await db.get("a/b") == {"at": 42, "y": 2}
        assert await db.get("a", {"shallow": "true"}) == {"b": True}
        await db.delete("a/b")
        assert await db.get("a/b") is None
        await db.aclose()

    run(go())


def test_conditional_put_and_lost_race() -> None:
    fake = FakeRtdb(sealed=False)

    async def go() -> None:
        db = fake.rtdb()
        value, tag = await db.get_etag("c")
        assert value is None
        assert tag == "null_etag"
        _, tag2 = await db.put_etag("c", {"v": 1}, tag)
        assert tag2 == etag({"v": 1})
        with pytest.raises(ConflictError) as lost:
            await db.put_etag("c", {"v": 2}, tag)
        assert lost.value.value == {"v": 1}
        assert lost.value.etag == tag2
        await db.delete("c", if_match=tag2)
        await db.aclose()

    run(go())


def test_http_errors_never_show_the_url_or_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = FakeRtdb(sealed=False)
    fake.fail[("GET", "/x")] = 500
    fake.raise_on.add(("PUT", "/y"))

    async def go() -> None:
        db = fake.rtdb()
        with pytest.raises(RtdbError, match=r"^GET x: HTTP 500$"):
            await db.get("x")
        with pytest.raises(RtdbError, match=r"^PUT y: ConnectError$"):
            await db.put("y", 1)
        await db.aclose()

    with caplog.at_level(logging.DEBUG):
        run(go())
    assert "test-token" not in caplog.text


def test_wrong_token_is_an_error() -> None:
    fake = FakeRtdb(sealed=False)
    fake.token = fake.token[::-1]

    async def go() -> None:
        db = fake.rtdb()
        with pytest.raises(RtdbError, match="HTTP 401"):
            await db.get("x")
        await db.aclose()

    run(go())


def test_default_client_is_created() -> None:
    async def token() -> str:
        return "t"

    async def go() -> None:
        db = Rtdb(DB + "/", token, root=ROOT)
        assert isinstance(db.client, httpx.AsyncClient)
        assert db.url("x") == f"{DB}/tutor/v1-e2e/x.json"
        with pytest.raises(RtdbError, match="GET x: "):
            await db.get("x")  # the test sandbox blocks real network
        await db.aclose()

    run(go())


def test_open_stream_errors() -> None:
    fake = FakeRtdb(sealed=False)
    fake.fail[("GET", "/s")] = 401
    fake.raise_on.add(("GET", "/t"))

    async def drain(db: Rtdb, path: str) -> list[str]:
        return [line async for line in db.open_stream(path)]

    async def go() -> None:
        db = fake.rtdb()
        with pytest.raises(RtdbError, match="STREAM s: HTTP 401"):
            await drain(db, "s")
        with pytest.raises(RtdbError, match="STREAM t: ConnectError"):
            await drain(db, "t")
        await db.aclose()

    run(go())


def test_open_stream_read_error_mid_stream() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        async def body() -> AsyncIterator[bytes]:
            yield b"event: keep-alive\n"
            msg = "cut"
            raise httpx.ReadError(msg, request=request)

        return httpx.Response(200, content=body())

    async def token() -> str:
        return "t"

    async def go() -> None:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        db = Rtdb(DB, token, client=client, root=ROOT)
        with pytest.raises(RtdbError, match="STREAM s: ReadError"):
            await _drain(db)
        await db.aclose()

    run(go())
