# Copyright (c) 2026 Krzysztof Rudnicki
"""EncryptingStore passthroughs, bulk reads and copy/open edge cases."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import pytest

from crdt_sync import (
    Argon2Params,
    E2eLayout,
    E2eLockedError,
    EncryptingStore,
    copy_to_encrypted,
    load_log,
    open_encrypted_client,
    reset_e2e_copy_memo,
    unlock_e2e,
)
from crdt_sync._e2e_store import _blobs, _fingerprint
from crdt_sync.tests.conftest import FakeStore, FakeStoreWithoutBulkRead

if TYPE_CHECKING:
    from collections.abc import Callable

    from crdt_sync import E2eKey, Hlc

PHRASE = "pw"
CHEAP = Argon2Params(8, 1, 1)
OLD = "app/devices"
LAYOUT = E2eLayout.of(OLD)
CLOCK = "2026-01-01T00:00:00.000Z-0000-pc"


def _log(title: str = "x", rid: str = "a") -> str:
    return json.dumps(
        {
            rid: {
                "id": rid,
                "fields": {"title": [title, CLOCK]},
                "deleted": False,
                "deleted_hlc": None,
            }
        }
    )


def _key(remote: FakeStore) -> E2eKey:
    return unlock_e2e(
        remote,
        path_prefix=LAYOUT.prefix,
        passphrase=PHRASE,
        params=CHEAP,
        e2e_path=LAYOUT.e2e_path,
    )


class HidingStore(FakeStore):
    """Lists every file but reads ``hidden`` paths as absent."""

    def __init__(self, files: dict[str, str], hidden: set[str]) -> None:
        super().__init__(files)
        self._hidden = hidden

    def get_file_text(self, path: str) -> str | None:
        if path in self._hidden:
            return None
        return super().get_file_text(path)


@pytest.fixture(autouse=True)
def _memo() -> None:
    reset_e2e_copy_memo()


def test_passthroughs_and_keyed_revisions() -> None:
    remote = FakeStore({"other/file": "raw"})
    store = EncryptingStore(remote, _key(remote), LAYOUT)
    assert store.list_directory("other") == ["file"]
    assert store.get_file_text("other/file") == "raw"
    assert store.get_file_text(f"{LAYOUT.prefix}/pc/log.json") is None
    assert store.can_access_remote()
    store.put_file_text(f"{LAYOUT.revs_path}/pc", "text", message="m")
    assert remote.files[f"{LAYOUT.revs_path}/pc"] == store.key.revision("text")
    store.put_file_text("other/file", "plain", message="m")
    assert remote.files["other/file"] == "plain"
    store.delete_file("other/file")
    assert "other/file" not in remote.files


def test_bulk_read_opens_sealed_and_drops_bad(
    caplog: pytest.LogCaptureFixture,
) -> None:
    remote = FakeStore()
    store = EncryptingStore(remote, _key(remote), LAYOUT)
    store.put_file_text(f"{LAYOUT.prefix}/pc", _log(), message="m")
    remote.files[f"{LAYOUT.prefix}/bad"] = '{"v": 2, "r": {}}'
    remote.files[f"{LAYOUT.revs_path}/pc"] = "rev"
    with caplog.at_level(logging.WARNING):
        out = store.get_string_map(LAYOUT.prefix)
    assert set(out) == {"pc"}
    assert set(load_log(out["pc"])) == {"a"}
    assert "Undecryptable entry" in caplog.text
    assert store.get_string_map(LAYOUT.revs_path) == {"pc": "rev"}


def test_bulk_read_is_empty_without_inner_support() -> None:
    remote = FakeStoreWithoutBulkRead()
    store = EncryptingStore(remote, _key(FakeStore()), LAYOUT)
    assert store.get_string_map(LAYOUT.prefix) == {}
    assert _fingerprint(remote, OLD) == ""


def test_blobs_cover_flat_nested_and_skipped_paths() -> None:
    remote = HidingStore(
        {
            f"{OLD}/flat": "f",
            f"{OLD}/gone": "g",
            f"{OLD}/pc/log.json": "n",
            f"{OLD}/pc/hidden.json": "h",
            "app/revs/pc": "r",
            f"{OLD}/e2e": "h",
            f"{OLD}/revs": "r",
        },
        {f"{OLD}/gone", f"{OLD}/pc/hidden.json"},
    )
    assert _blobs(remote, OLD) == {"flat": "f", "pc/log.json": "n"}


def test_copy_skips_unreadable_and_flat_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    remote = FakeStore({f"{OLD}/flat": _log(), f"{OLD}/pc/log.json": "not json"})
    with caplog.at_level(logging.WARNING):
        copied = copy_to_encrypted(remote, _key(remote), OLD, LAYOUT)
    assert copied == 1
    assert "Unreadable old log" in caplog.text
    assert f"{LAYOUT.prefix}/flat" in remote.files
    assert f"{LAYOUT.prefix}/pc/log.json" not in remote.files


def test_changed_old_prefix_is_copied_again() -> None:
    remote = FakeStore({f"{OLD}/pc/log.json": _log("one")})
    open_encrypted_client(remote, OLD, passphrase=PHRASE, params=CHEAP)
    remote.files[f"{OLD}/pc/log.json"] = _log("two", rid="b")
    remote.files["app/revs/pc"] = "newer"
    store, layout = open_encrypted_client(remote, OLD, passphrase=PHRASE, params=CHEAP)
    text = store.get_file_text(f"{layout.prefix}/pc/log.json")
    assert text is not None
    assert set(load_log(text)) == {"a", "b"}


def test_unchanged_prefix_is_not_copied_twice() -> None:
    remote = FakeStore({f"{OLD}/pc/log.json": _log()})
    open_encrypted_client(remote, OLD, passphrase=PHRASE, params=CHEAP)
    remote.writes.clear()
    open_encrypted_client(remote, OLD, passphrase=PHRASE, params=CHEAP)
    assert remote.writes == []


def test_unreadable_header_locks_the_client() -> None:
    remote = FakeStore({LAYOUT.e2e_path: "not json"})
    with pytest.raises(E2eLockedError, match="not JSON"):
        open_encrypted_client(remote, OLD, passphrase=PHRASE, params=CHEAP)


def test_copy_never_overwrites_non_log_and_skips_empty() -> None:
    layout = E2eLayout.of("app/devices")
    remote = FakeStore(
        {
            "app/devices/pc/current.json": "{}",
            "app/devices-e2e/pc/current.json": '{"photos":["a"]}',
            "app/devices/tab/current.json": "{}",
        }
    )
    key = unlock_e2e(
        remote,
        path_prefix=layout.prefix,
        passphrase="x" * 8,
        params=Argon2Params(8, 1, 1),
        e2e_path=layout.e2e_path,
    )
    assert copy_to_encrypted(remote, key, "app/devices", layout) == 0
    assert remote.files["app/devices-e2e/pc/current.json"] == '{"photos":["a"]}'
    assert "app/devices-e2e/tab/current.json" not in remote.files


def test_copy_leaves_a_non_log_destination_alone(
    make_hlc: Callable[..., Hlc],
) -> None:
    layout = E2eLayout.of("app/devices")
    log = {
        "n": {
            "id": "n",
            "fields": {"t": ["x", make_hlc(1).to_str()]},
            "deleted": False,
            "deleted_hlc": None,
        }
    }
    remote = FakeStore(
        {
            "app/devices/pc/current.json": json.dumps(log),
            "app/devices-e2e/pc/current.json": '{"photos":["a"]}',
        }
    )
    key = unlock_e2e(
        remote,
        path_prefix=layout.prefix,
        passphrase="x" * 8,
        params=Argon2Params(8, 1, 1),
        e2e_path=layout.e2e_path,
    )
    assert copy_to_encrypted(remote, key, "app/devices", layout) == 0
    assert remote.files["app/devices-e2e/pc/current.json"] == '{"photos":["a"]}'
