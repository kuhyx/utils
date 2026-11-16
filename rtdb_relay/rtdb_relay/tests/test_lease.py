# Copyright (c) 2026 Krzysztof Rudnicki. MIT License.
"""The claim lease: take, lose a race, renew, lose the lease."""

from __future__ import annotations

import asyncio
import logging

import pytest

from rtdb_relay.lease import Lease, claimable, ms, valid_rid
from rtdb_relay.rtdb import ConflictError
from rtdb_relay.tests._fake_rtdb import ROOT, FakeRtdb

RID = "01J0000000000000000000000R"


def test_helpers() -> None:
    assert valid_rid(RID)
    assert not valid_rid("../x")
    assert ms(1.5) == 1500
    assert claimable(None, 0)
    assert claimable({"lease_until": 999}, 1.0)
    assert not claimable({"lease_until": 2000, "by": "x"}, 1.0)
    assert claimable({"lease_until": 2000, "by": "me"}, 1.0, "me")
    assert claimable({"lease_until": "?"}, 1.0)


def test_take_renew_and_races(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeRtdb()

    async def go() -> None:
        db = fake.rtdb()
        lease = Lease(db, RID, "pc", lambda: 1.0)
        fake.set(f"{ROOT}/{lease.path}", {"attempt": 2, "lease_until": 0})
        assert await lease.take()
        assert lease.attempt == 3
        await lease.renew("running")
        assert fake.get(f"{ROOT}/{lease.path}")["phase"] == "running"
        fake.set(f"{ROOT}/{lease.path}", {"by": "other", "lease_until": 9e15})
        await lease.renew()  # lost: only logged
        assert fake.get(f"{ROOT}/{lease.path}")["by"] == "other"
        assert not await Lease(db, RID, "pc", lambda: 1.0).take()
        fake.set(f"{ROOT}/{lease.path}", {"attempt": "x"})

        async def lose(*args: object) -> tuple[object, str]:
            raise ConflictError("p", None, "")

        monkeypatch.setattr(db, "put_etag", lose)
        racer = Lease(db, RID, "pc", lambda: 1.0)
        assert not await racer.take()
        assert racer.attempt == 1
        await db.aclose()

    with caplog.at_level(logging.WARNING):
        asyncio.run(go())
    assert "lost to another writer" in caplog.text
    assert "claimed" in caplog.text
