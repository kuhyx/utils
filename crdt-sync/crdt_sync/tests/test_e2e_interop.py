# Copyright (c) 2026 Krzysztof Rudnicki
"""Cross-language golden vectors: Python opens what Dart sealed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from crdt_sync import (
    E2eDecryptError,
    E2eKey,
    E2eWrongPassphraseError,
    open_log_text,
    seal_log_text,
    unlock_e2e,
)
from crdt_sync.tests.conftest import FakeStore as MemoryRemote

WRONG = "nope"
VECTORS = json.loads(
    (Path(__file__).parent / "fixtures" / "e2e_dart_vectors.json").read_text(
        encoding="utf-8"
    )
)


def _key() -> E2eKey:
    remote = MemoryRemote({"vec/e2e": VECTORS["header"]})
    return unlock_e2e(
        remote,
        path_prefix="vec/notes-e2e",
        passphrase=str(VECTORS["passphrase"]),
        e2e_path="vec/e2e",
    )


def test_argon2id_and_hkdf_match_dart() -> None:
    assert _key().master.hex() == VECTORS["master_hex"]


def test_keyed_revision_matches_dart() -> None:
    assert _key().revision("abc") == VECTORS["revision_of_abc"]


def test_opens_a_dart_envelope() -> None:
    opened = open_log_text(VECTORS["envelope"], _key().cipher(), path=VECTORS["path"])
    assert json.loads(opened) == json.loads(VECTORS["log"])


def test_opens_a_dart_whole_blob() -> None:
    opened = open_log_text(VECTORS["whole"], _key().cipher(), path=VECTORS["path"])
    assert opened == "not a log"


def test_wrong_passphrase_is_refused() -> None:
    remote = MemoryRemote({"vec/e2e": VECTORS["header"]})
    with pytest.raises(E2eWrongPassphraseError):
        unlock_e2e(remote, path_prefix="x", passphrase=WRONG, e2e_path="vec/e2e")


def test_a_moved_envelope_is_refused() -> None:
    with pytest.raises(E2eDecryptError):
        open_log_text(VECTORS["envelope"], _key().cipher(), path="vec/other")


def test_python_round_trip() -> None:
    cipher = _key().cipher()
    sealed = seal_log_text(VECTORS["log"], cipher, path=VECTORS["path"])
    assert "buy milk" not in sealed
    assert json.loads(open_log_text(sealed, cipher, path=VECTORS["path"])) == (
        json.loads(VECTORS["log"])
    )
