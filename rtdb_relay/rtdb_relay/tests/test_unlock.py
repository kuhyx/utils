# Copyright (c) 2026 Krzysztof Rudnicki. MIT License.
"""Unlocking: header made once, wrong or missing passphrase refused."""

from __future__ import annotations

import asyncio

from crdt_sync import Argon2Params, E2eLayout, E2eLockedError
import pytest

from rtdb_relay.tests._fake_rtdb import FakeRtdb
from rtdb_relay.unlock import HeaderStore, unlock

FAST = Argon2Params(memory_kib=8, iterations=1, parallelism=1)
LAYOUT = E2eLayout.of("tutor/v1")


def test_unlock_creates_the_header_then_refuses_a_wrong_passphrase() -> None:
    fake = FakeRtdb(sealed=False)

    async def go() -> None:
        db = fake.rtdb()
        key = await unlock(db, "pw", LAYOUT, FAST)
        header = fake.raw_get(LAYOUT.e2e_path)
        assert isinstance(header, str)
        assert "argon2id" in header
        again = await unlock(db, "pw", LAYOUT, FAST)
        assert again.master == key.master
        with pytest.raises(E2eLockedError):
            await unlock(db, "other", LAYOUT, FAST)
        with pytest.raises(E2eLockedError):
            await unlock(db, "", LAYOUT, FAST)
        fake.raw_set(LAYOUT.e2e_path, {"not": "a header"})
        with pytest.raises(E2eLockedError):
            await unlock(db, "pw", LAYOUT, FAST)
        await db.aclose()

    asyncio.run(go())


def test_header_store_lists_nothing_and_never_deletes() -> None:
    fake = FakeRtdb(sealed=False)

    async def go() -> None:
        db = fake.rtdb()
        store = HeaderStore(db.at(""), asyncio.get_running_loop())
        assert store.list_directory("x") == []
        assert store.can_access_remote()
        with pytest.raises(NotImplementedError):
            store.delete_file("x")
        await db.aclose()

    asyncio.run(go())
