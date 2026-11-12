# Copyright (c) 2026 Krzysztof Rudnicki
"""E2eCipher blob errors and the per-record envelope's edge shapes."""

from __future__ import annotations

import base64
import json

import pytest

from crdt_sync import (
    E2eCipher,
    E2eDecryptError,
    is_e2e_envelope,
    open_log_text,
    seal_log_text,
)

PATH = "app/devices-e2e/pc/log.json"
CLOCK = "2026-01-01T00:00:00.000Z-0000-pc"


def _cipher(*, accept_plaintext: bool = True) -> E2eCipher:
    return E2eCipher(bytes(range(32)), accept_plaintext=accept_plaintext)


def _blob(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def _log(**records: object) -> str:
    return json.dumps(records)


def _record(rid: str = "a", **extra: object) -> dict[str, object]:
    return {
        "id": rid,
        "fields": {"title": ["x", CLOCK]},
        "deleted": False,
        "deleted_hlc": None,
        **extra,
    }


def test_key_must_be_32_bytes() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        E2eCipher(b"short")


def test_blob_round_trips() -> None:
    cipher = _cipher()
    assert cipher.open(cipher.seal("héllo", path=PATH), path=PATH) == "héllo"


def test_plaintext_is_read_only_while_accepted() -> None:
    assert _cipher().open('{"a": 1}', path=PATH) == '{"a": 1}'
    with pytest.raises(E2eDecryptError, match="after migration"):
        _cipher(accept_plaintext=False).open("[1]", path=PATH)


@pytest.mark.parametrize(
    ("stored", "message"),
    [
        ("!!not base64!!", "neither JSON nor base64"),
        ("", "empty blob"),
        (_blob(b"\x02" + bytes(60)), "uses format 2"),
        (_blob(b"\x01" + bytes(10)), "truncated"),
        (_blob(b"\x01" + bytes(60)), "failed authentication"),
    ],
)
def test_bad_blobs_are_refused(stored: str, message: str) -> None:
    with pytest.raises(E2eDecryptError, match=message):
        _cipher().open(stored, path=PATH)


def test_blob_is_bound_to_its_path() -> None:
    sealed = _cipher().seal("secret", path=PATH)
    with pytest.raises(E2eDecryptError, match="failed authentication"):
        _cipher().open(sealed, path="other")


@pytest.mark.parametrize("text", ["not json", "[1]", '{"v": true}', '{"v": "1"}', "{}"])
def test_non_envelopes_are_detected(text: str) -> None:
    assert not is_e2e_envelope(text)


def test_envelope_is_detected() -> None:
    assert is_e2e_envelope('{"v": 1}')


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[1]",
        _log(a=[1]),
        _log(a=_record("b")),
        _log(a={"id": "a", "fields": []}),
    ],
)
def test_non_log_text_is_sealed_whole(text: str) -> None:
    sealed = seal_log_text(text, _cipher(), path=PATH)
    assert "b" in json.loads(sealed)
    assert open_log_text(sealed, _cipher(), path=PATH) == text


def test_record_without_fields_has_no_newest_clock() -> None:
    empty = {"id": "a", "fields": {}, "deleted": True, "deleted_hlc": CLOCK}
    sealed = seal_log_text(_log(a=empty), _cipher(), path=PATH)
    assert json.loads(sealed)["r"]["a"]["h"] is None
    opened = json.loads(open_log_text(sealed, _cipher(), path=PATH))
    assert opened == {"a": empty}


def test_plaintext_log_passes_or_fails_by_policy() -> None:
    text = _log(a=_record())
    assert open_log_text(text, _cipher(), path=PATH) == text
    with pytest.raises(E2eDecryptError, match="after migration"):
        open_log_text(text, _cipher(accept_plaintext=False), path=PATH)


def test_unknown_envelope_version_is_refused() -> None:
    with pytest.raises(E2eDecryptError, match="uses format 2"):
        open_log_text('{"v": 2, "r": {}}', _cipher(), path=PATH)


def test_envelope_without_records_is_misshaped() -> None:
    with pytest.raises(E2eDecryptError, match="mis-shaped"):
        open_log_text('{"v": 1, "b": 5, "r": []}', _cipher(), path=PATH)


@pytest.mark.parametrize(
    "record",
    [[], {"p": "x", "d": 1}, {"d": False}, {"p": 3, "d": False}],
)
def test_misshaped_record_is_refused(record: object) -> None:
    text = json.dumps({"v": 1, "r": {"a": record}})
    with pytest.raises(E2eDecryptError, match="record a"):
        open_log_text(text, _cipher(), path=PATH)


def test_tampered_record_metadata_fails_authentication() -> None:
    sealed = json.loads(seal_log_text(_log(a=_record()), _cipher(), path=PATH))
    sealed["r"]["a"]["d"] = True
    with pytest.raises(E2eDecryptError, match="failed authentication"):
        open_log_text(json.dumps(sealed), _cipher(), path=PATH)
