# Copyright (c) 2026 Krzysztof Rudnicki
"""Clearing an old plaintext prefix only after the encrypted copy is proven."""

from __future__ import annotations

import io
import json

import pytest

from crdt_sync import (
    Argon2Params,
    E2eLayout,
    E2eLockedError,
    clear_plaintext_prefix,
    copy_to_encrypted,
    unlock_e2e,
    unverified_blobs,
)
from crdt_sync.tests.conftest import FakeStore
from tool import e2e_cleanup

CHEAP = Argon2Params(8, 1, 1)
PHRASE = "pw"
WRONG = PHRASE + "x"
OLD = "app/devices"
LAYOUT = E2eLayout.of(OLD)


def _log(title: str, stamp: str = "2026-01-01T00:00:00.000Z") -> str:
    return json.dumps(
        {
            "n": {
                "id": "n",
                "fields": {"t": [title, f"{stamp}-0000-a"]},
                "deleted": False,
                "deleted_hlc": None,
            }
        }
    )


def _seeded() -> FakeStore:
    remote = FakeStore({f"{OLD}/pc/log.json": _log("x"), "app/revs/pc": "r"})
    key = unlock_e2e(
        remote,
        path_prefix=LAYOUT.prefix,
        passphrase=PHRASE,
        params=CHEAP,
        e2e_path=LAYOUT.e2e_path,
    )
    copy_to_encrypted(remote, key, OLD, LAYOUT)
    return remote


def test_dry_run_lists_and_deletes_nothing() -> None:
    remote = _seeded()
    paths = clear_plaintext_prefix(remote, OLD, passphrase=PHRASE, apply=False)
    assert paths == [f"{OLD}/pc/log.json"]
    assert f"{OLD}/pc/log.json" in remote.files


def test_apply_deletes_only_after_verification() -> None:
    remote = _seeded()
    clear_plaintext_prefix(remote, OLD, passphrase=PHRASE, apply=True)
    assert f"{OLD}/pc/log.json" not in remote.files
    assert f"{LAYOUT.prefix}/pc/log.json" in remote.files


def test_unverified_copy_refuses() -> None:
    remote = _seeded()
    remote.files[f"{OLD}/pc/log.json"] = _log("newer", "2026-02-01T00:00:00.000Z")
    remote.files[f"{OLD}/bad/log.json"] = "{oops"
    key = unlock_e2e(
        remote, path_prefix=LAYOUT.prefix, passphrase=PHRASE, e2e_path=LAYOUT.e2e_path
    )
    assert unverified_blobs(remote, key, OLD, LAYOUT) == ["bad/log.json", "pc/log.json"]
    with pytest.raises(E2eLockedError, match="not verified"):
        clear_plaintext_prefix(remote, OLD, passphrase=PHRASE, apply=True)
    assert f"{OLD}/pc/log.json" in remote.files


def test_empty_logs_need_no_copy() -> None:
    remote = _seeded()
    remote.files[f"{OLD}/tab/log.json"] = "{}"
    paths = clear_plaintext_prefix(remote, OLD, passphrase=PHRASE, apply=False)
    assert f"{OLD}/tab/log.json" in paths


def test_never_creates_a_header_and_wrong_passphrase_locks() -> None:
    remote = FakeStore({f"{OLD}/pc/log.json": _log("x")})
    with pytest.raises(E2eLockedError, match="no e2e header"):
        clear_plaintext_prefix(remote, OLD, passphrase=PHRASE, apply=False)
    assert LAYOUT.e2e_path not in remote.files
    seeded = _seeded()
    with pytest.raises(E2eLockedError):
        clear_plaintext_prefix(seeded, OLD, passphrase=WRONG, apply=False)


def test_tool_main(monkeypatch: pytest.MonkeyPatch) -> None:
    remote = _seeded()
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    assert e2e_cleanup.run(remote, OLD, PHRASE, apply=False) == 0
    assert "would delete 1" in out.getvalue()
    assert e2e_cleanup.run(remote, OLD, PHRASE, apply=True) == 0
    assert "deleted 1" in out.getvalue()
    assert e2e_cleanup.run(FakeStore(), OLD, PHRASE, apply=True) == 1
