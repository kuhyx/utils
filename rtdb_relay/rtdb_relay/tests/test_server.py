# Copyright (c) 2026 Krzysztof Rudnicki. MIT License.
"""The request server: claim, run the kind's handler, write the result."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest

from rtdb_relay import server as server_mod
from rtdb_relay.server import RequestError, RequestServer
from rtdb_relay.tests._fake_rtdb import ROOT, FakeRtdb

RID = "01J0000000000000000000000R"
NOW = 1_800_000_000.0


async def _echo(body: dict[str, Any]) -> dict[str, Any]:
    return {"echo": body.get("x")}


async def _refuse(body: dict[str, Any]) -> dict[str, Any]:
    raise RequestError("not_now", "cannot start", retry=True)


async def _bug(body: dict[str, Any]) -> dict[str, Any]:
    raise KeyError(body["missing"])


HANDLERS = {"echo": _echo, "refuse": _refuse, "bug": _bug}


def _req(kind: str, body: object = None) -> dict[str, Any]:
    return {"kind": kind, "dev": "d1", "created": 1, "sent_at": 1, "body": body}


def _answer(fake: FakeRtdb, rid: str = RID) -> dict[str, Any] | None:
    async def go() -> dict[str, Any] | None:
        db = fake.rtdb()
        srv = RequestServer(db, "pc", HANDLERS, now=lambda: NOW)
        node = await srv._raw.get(f"requests/{rid}")
        out = await srv.answer(rid, node if isinstance(node, dict) else {})
        await db.aclose()
        return out

    return asyncio.run(go())


@pytest.mark.parametrize(
    ("kind", "body", "want"),
    [
        ("echo", {"x": 7}, {"ok": True, "kind": "echo", "echo": 7}),
        ("echo", "not a dict", {"ok": True, "kind": "echo"}),
        ("nope", None, {"ok": False, "kind": "nope", "code": "unknown_kind"}),
        ("refuse", {}, {"ok": False, "code": "not_now", "retry": True}),
        ("bug", {}, {"ok": False, "code": "internal", "error": "KeyError"}),
    ],
)
def test_answers_by_kind(kind: str, body: object, want: dict[str, Any]) -> None:
    fake = FakeRtdb()
    fake.set(f"{ROOT}/requests/{RID}/req", _req(kind, body))
    assert _answer(fake) is not None
    result = fake.get(f"{ROOT}/requests/{RID}/result")
    assert want.items() <= result.items()
    assert result["at"] == fake.now_ms
    claim = fake.get(f"{ROOT}/requests/{RID}/claim")
    assert claim["by"] == "pc"
    assert claim["attempt"] == 1


def test_refuses_an_unsealed_request_and_skips_what_is_not_pending() -> None:
    fake = FakeRtdb()
    fake.raw_set(f"{ROOT}/requests/{RID}/req", _req("echo", {"x": 1}))
    assert _answer(fake) is not None
    assert fake.get(f"{ROOT}/requests/{RID}/result")["code"] == "unsealed"
    assert _answer(fake) is None  # already has a result
    assert _answer(fake, "not-a-ulid") is None
    fake2 = FakeRtdb()
    fake2.set(f"{ROOT}/requests/{RID}/claim", {"by": "other", "lease_until": 9e15})
    assert _answer(fake2) is None  # no req
    fake2.set(f"{ROOT}/requests/{RID}/req", _req("echo"))
    assert _answer(fake2) is None  # another worker holds the lease


def test_wrong_key_request_reads_as_unsealed() -> None:
    fake = FakeRtdb()
    fake.raw_set(f"{ROOT}/requests/{RID}/req", {"_e2e": "AQ==", "created": 1})
    _answer(fake)
    assert fake.get(f"{ROOT}/requests/{RID}/result")["code"] == "unsealed"


def test_run_serves_new_requests_and_renews_long_leases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_mod, "RENEW_S", 0.01)
    fake = FakeRtdb()
    seen: list[str] = []

    async def slow(body: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0.05)
        claim = fake.get(f"{ROOT}/requests/{RID}/claim")
        seen.append(claim["phase"])
        return {}

    async def go() -> None:
        db = fake.rtdb()
        srv = RequestServer(db, "pc", {"slow": slow})
        task = asyncio.create_task(srv.run())
        await asyncio.sleep(0.01)
        await db.put(f"requests/{RID}/req", _req("slow"))
        for _ in range(200):
            if fake.get(f"{ROOT}/requests/{RID}/result"):
                break
            await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await db.aclose()

    asyncio.run(go())
    assert fake.get(f"{ROOT}/requests/{RID}/result")["ok"] is True
    assert seen == ["running"]


def test_dispatch_skips_busy_and_logs_a_failing_request(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = FakeRtdb()

    async def go() -> None:
        db = fake.rtdb()
        srv = RequestServer(db, "pc", HANDLERS)

        async def boom(rid: str, node: dict[str, Any]) -> None:
            raise RuntimeError(rid)

        srv.answer = boom  # type: ignore[method-assign]
        srv.dispatch({RID: {"req": {}}, "x": "flat", "y": {"result": {}}})
        srv.dispatch({RID: {"req": {}}})  # in flight: not started twice
        assert len(srv.tasks) == 1
        await asyncio.gather(*srv.tasks)
        await db.aclose()

    with caplog.at_level(logging.ERROR):
        asyncio.run(go())
    assert f"request {RID} failed" in caplog.text
