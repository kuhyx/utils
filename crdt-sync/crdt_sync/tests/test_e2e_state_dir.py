# Copyright (c) 2026 Krzysztof Rudnicki
"""A per-minute daemon must not pay Argon2id or a full copy every tick."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from crdt_sync import Argon2Params, E2eLockedError, open_encrypted_client
from crdt_sync import _e2e_key as key_mod
from crdt_sync import _e2e_store as store_mod
from crdt_sync.tests.conftest import FakeStore

if TYPE_CHECKING:
    from pathlib import Path

    from crdt_sync import E2eKey, RemoteStore

CHEAP = Argon2Params(8, 1, 1)
PHRASE = "pw"
WRONG = PHRASE + "x"
LOG = json.dumps(
    {
        "a": {
            "id": "a",
            "fields": {"t": ["x", "2026-01-01T00:00:00.000Z-0000-a"]},
            "deleted": False,
            "deleted_hlc": None,
        }
    }
)


def test_state_dir_caches_key_and_copy_across_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = FakeStore({"app/devices/pc/log.json": LOG, "app/revs/pc": "r1"})
    derives: list[int] = []
    real = key_mod.unlock_e2e

    def counting(
        remote: RemoteStore,
        *,
        path_prefix: str,
        passphrase: str,
        params: Argon2Params | None = None,
        e2e_path: str | None = None,
    ) -> E2eKey:
        derives.append(1)
        return real(
            remote,
            path_prefix=path_prefix,
            passphrase=passphrase,
            params=params,
            e2e_path=e2e_path,
        )

    monkeypatch.setattr(store_mod, "unlock_e2e", counting)
    for _ in range(3):
        store_mod.reset_e2e_copy_memo()  # a fresh process each tick
        remote.writes.clear()
        open_encrypted_client(
            remote, "app/devices", passphrase=PHRASE, params=CHEAP, state_dir=tmp_path
        )
    assert derives == [1]
    assert remote.writes == []
    key_files = list(tmp_path.glob("e2e-*.key"))
    assert len(key_files) == 1
    assert key_files[0].stat().st_mode & 0o777 == 0o600


def test_stale_cached_key_rederives(tmp_path: Path) -> None:
    remote = FakeStore()
    open_encrypted_client(
        remote, "app/devices", passphrase=PHRASE, params=CHEAP, state_dir=tmp_path
    )
    for key_file in tmp_path.glob("e2e-*.key"):
        key_file.write_text("00" * 32, encoding="utf-8")
    store, _ = open_encrypted_client(
        remote, "app/devices", passphrase=PHRASE, params=CHEAP, state_dir=tmp_path
    )
    assert next(tmp_path.glob("e2e-*.key")).read_text(encoding="utf-8") == (
        store.key.master.hex()
    )


def test_garbage_cached_key_is_ignored_and_wrong_passphrase_locks(
    tmp_path: Path,
) -> None:
    remote = FakeStore()
    open_encrypted_client(
        remote, "app/devices", passphrase=PHRASE, params=CHEAP, state_dir=tmp_path
    )
    for key_file in tmp_path.glob("e2e-*.key"):
        key_file.write_text("not hex", encoding="utf-8")
    with pytest.raises(E2eLockedError):
        open_encrypted_client(
            remote, "app/devices", passphrase=WRONG, params=CHEAP, state_dir=tmp_path
        )
