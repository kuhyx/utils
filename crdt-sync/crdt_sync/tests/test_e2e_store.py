# Copyright (c) 2026 Krzysztof Rudnicki
"""EncryptingStore, layout, one-time copy and open, mirroring the Dart side."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from crdt_sync import (
    Argon2Params,
    E2eLayout,
    E2eLockedError,
    EncryptingStore,
    LogCodec,
    SyncTarget,
    copy_to_encrypted,
    dump_log,
    load_log,
    open_encrypted_client,
    reset_e2e_copy_memo,
    sync_log,
    unlock_e2e,
)
from crdt_sync.tests.conftest import FakeStore

if TYPE_CHECKING:
    from collections.abc import Callable

    from crdt_sync import Hlc

PHRASE = "pw"
WRONG = "bad"
CHEAP = Argon2Params(8, 1, 1)
OLD = "app/devices"


def _log_text(make_hlc: Callable[..., Hlc], **titles: str) -> str:
    return json.dumps(
        {
            rid: {
                "id": rid,
                "fields": {"title": [t, make_hlc(1000).to_str()]},
                "deleted": False,
                "deleted_hlc": None,
            }
            for rid, t in titles.items()
        }
    )


@pytest.fixture(autouse=True)
def _memo() -> None:
    reset_e2e_copy_memo()


def test_layouts() -> None:
    assert E2eLayout.of("app/devices") == E2eLayout(
        "app/devices-e2e", "app/revs-e2e", "app/e2e"
    )
    assert E2eLayout.of("settings-sync") == E2eLayout(
        "settings-sync-e2e", "settings-sync-e2e/revs", "settings-sync-e2e/e2e"
    )


def test_sync_through_store_is_ciphertext_and_merges(
    make_hlc: Callable[..., Hlc],
) -> None:
    remote = FakeStore()
    layout = E2eLayout.of(OLD)
    key = unlock_e2e(
        remote,
        path_prefix=layout.prefix,
        passphrase=PHRASE,
        params=CHEAP,
        e2e_path=layout.e2e_path,
    )
    store = EncryptingStore(remote, key, layout)
    codec = LogCodec(encode=dump_log, decode=load_log, filename="log.json")
    phone = load_log(_log_text(make_hlc, n1="buy milk"))
    sync_log(SyncTarget(store, "phone", layout.prefix), phone, codec)
    blob = remote.files[f"{layout.prefix}/phone/log.json"]
    assert "buy milk" not in blob
    assert '"title"' not in blob
    merged = sync_log(SyncTarget(store, "pc", layout.prefix), {}, codec)
    assert set(merged) == {"n1"}


def test_open_copies_old_prefix_once_and_locks_without_password(
    make_hlc: Callable[..., Hlc],
) -> None:
    remote = FakeStore({f"{OLD}/pc/log.json": _log_text(make_hlc, a="x")})
    with pytest.raises(E2eLockedError):
        open_encrypted_client(remote, OLD, passphrase="", params=CHEAP)
    store, layout = open_encrypted_client(remote, OLD, passphrase=PHRASE, params=CHEAP)
    text = store.get_file_text(f"{layout.prefix}/pc/log.json")
    assert text is not None
    assert set(load_log(text)) == {"a"}
    assert "x" in remote.files[f"{OLD}/pc/log.json"]
    with pytest.raises(E2eLockedError):
        open_encrypted_client(remote, OLD, passphrase=WRONG, params=CHEAP)


def test_copy_is_idempotent(make_hlc: Callable[..., Hlc]) -> None:
    remote = FakeStore({f"{OLD}/pc/log.json": _log_text(make_hlc, a="x")})
    layout = E2eLayout.of(OLD)
    key = unlock_e2e(
        remote,
        path_prefix=layout.prefix,
        passphrase=PHRASE,
        params=CHEAP,
        e2e_path=layout.e2e_path,
    )
    assert copy_to_encrypted(remote, key, OLD, layout) == 1
    remote.writes.clear()
    assert copy_to_encrypted(remote, key, OLD, layout) == 0
    assert remote.writes == []
