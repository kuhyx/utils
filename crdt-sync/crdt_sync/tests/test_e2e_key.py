# Copyright (c) 2026 Krzysztof Rudnicki
"""Argon2id key, header parsing and unlock edge cases."""

from __future__ import annotations

import json

import pytest

from crdt_sync import (
    Argon2Params,
    E2eHeaderError,
    E2eKey,
    E2eWrongPassphraseError,
    default_e2e_path,
    unlock_e2e,
)
from crdt_sync._e2e_key import key_matches, read_header
from crdt_sync.tests.conftest import FakeStore

CHEAP = Argon2Params(8, 1, 1)
HEADER = {
    "v": 1,
    "kdf": "argon2id",
    "salt": "AAAAAAAAAAAAAAAAAAAAAA==",
    "m": 8,
    "t": 1,
    "p": 1,
    "check": "c",
}


def _unlock(remote: FakeStore, phrase: str = "pw") -> E2eKey:
    return unlock_e2e(
        remote,
        path_prefix="app/devices-e2e",
        passphrase=phrase,
        params=CHEAP,
        e2e_path="app/e2e",
    )


class RacedStore(FakeStore):
    """Another device's header wins the first write."""

    def __init__(self, winner: str) -> None:
        super().__init__()
        self._winner = winner

    def put_file_text(self, path: str, text: str, *, message: str) -> None:
        super().put_file_text(path, self._winner, message=message)


def test_default_path_is_a_sibling_or_nested() -> None:
    assert default_e2e_path("app/devices-e2e") == "app/e2e"
    assert default_e2e_path("flat") == "flat/e2e"


def test_master_key_must_be_32_bytes() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        E2eKey.from_bytes(b"short")


def test_unlock_refuses_an_empty_passphrase() -> None:
    with pytest.raises(ValueError, match="empty"):
        _unlock(FakeStore(), "")


def test_unlock_creates_then_reuses_the_header() -> None:
    remote = FakeStore()
    first = _unlock(remote)
    assert _unlock(remote).master == first.master
    assert key_matches(first, remote, "app/e2e")
    assert not key_matches(_unlock(FakeStore(), "other"), remote, "app/e2e")


def test_missing_header_matches_nothing() -> None:
    key = E2eKey.from_bytes(bytes(32))
    assert read_header(FakeStore(), "app/e2e") is None
    assert not key_matches(key, FakeStore(), "app/e2e")


def test_wrong_passphrase_is_refused() -> None:
    remote = FakeStore()
    _unlock(remote)
    with pytest.raises(E2eWrongPassphraseError):
        _unlock(remote, "nope")


def test_losing_the_header_race_adopts_the_winner() -> None:
    winner = FakeStore()
    key = _unlock(winner)
    raced = RacedStore(winner.files["app/e2e"])
    assert _unlock(raced).master == key.master
    with pytest.raises(E2eWrongPassphraseError):
        _unlock(RacedStore(winner.files["app/e2e"]), "nope")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("not json", "not JSON"),
        ("[1]", "known version"),
        (json.dumps({**HEADER, "v": 2}), "known version"),
        (json.dumps({**HEADER, "kdf": "scrypt"}), "malformed"),
        (json.dumps({k: v for k, v in HEADER.items() if k != "m"}), "malformed"),
        (json.dumps({**HEADER, "m": "x"}), "malformed"),
        (json.dumps({**HEADER, "salt": "A"}), "malformed"),
    ],
)
def test_bad_headers_are_refused(text: str, message: str) -> None:
    remote = FakeStore({"app/e2e": text})
    with pytest.raises(E2eHeaderError, match=message):
        read_header(remote, "app/e2e")
    with pytest.raises(E2eHeaderError, match=message):
        _unlock(remote)


def test_a_good_header_parses() -> None:
    header = read_header(FakeStore({"app/e2e": json.dumps(HEADER)}), "app/e2e")
    assert header is not None
    assert header.params == CHEAP
    assert header.check == "c"
