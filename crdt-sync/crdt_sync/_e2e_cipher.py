# Copyright (c) 2026 Krzysztof Rudnicki
"""XChaCha20-Poly1305 blob cipher and per-record envelope.

Byte-compatible with ``crdt_sync_dart``'s ``E2eCipher`` and
``sealLogText``/``openLogText``: a blob is base64 ``[version][nonce][ct][tag]``
with ``[version] + utf8(path)`` as AAD; an envelope keeps record ids, the
tombstone and the newest HLC clear and seals each record's fields.
"""

from __future__ import annotations

import base64
import binascii
import json
import secrets
from typing import cast

from nacl.bindings import (
    crypto_aead_xchacha20poly1305_ietf_decrypt,
    crypto_aead_xchacha20poly1305_ietf_encrypt,
)
from nacl.exceptions import CryptoError

from crdt_sync._hlc import Hlc

E2E_FORMAT_VERSION = 1
_NONCE = 24
_TAG = 16
_KEY = 32


class E2eDecryptError(ValueError):
    """A blob that is tampered, under another key, or in an unknown format.

    A ``ValueError`` so the pull loop skips the peer instead of aborting.
    """


def is_plaintext(stored: str) -> bool:
    """Return whether ``stored`` is legacy JSON rather than a sealed blob."""
    return stored.lstrip().startswith(("{", "["))


def _aad(version: int, path: str) -> bytes:
    return bytes([version]) + path.encode()


class E2eCipher:
    """Seals and opens blobs bound to their remote path."""

    def __init__(self, key: bytes, *, accept_plaintext: bool = True) -> None:
        """Wrap a 32-byte ``key``; ``accept_plaintext`` reads old peers."""
        if len(key) != _KEY:
            msg = "key must be 32 bytes"
            raise ValueError(msg)
        self._key = bytes(key)
        self.accept_plaintext = accept_plaintext

    def seal(self, plaintext: str, *, path: str) -> str:
        """Return ``plaintext`` sealed for ``path``."""
        nonce = secrets.token_bytes(_NONCE)
        box = crypto_aead_xchacha20poly1305_ietf_encrypt(
            plaintext.encode(), _aad(E2E_FORMAT_VERSION, path), nonce, self._key
        )
        return base64.b64encode(bytes([E2E_FORMAT_VERSION]) + nonce + box).decode()

    def open(self, stored: str, *, path: str) -> str:
        """Return the plaintext of ``stored``; raise :class:`E2eDecryptError`."""
        if is_plaintext(stored):
            if self.accept_plaintext:
                return stored
            msg = f"plaintext blob at {path} after migration"
            raise E2eDecryptError(msg)
        try:
            raw = base64.b64decode(stored, validate=True)
        except binascii.Error as exc:
            msg = f"blob at {path} is neither JSON nor base64"
            raise E2eDecryptError(msg) from exc
        if not raw:
            msg = f"empty blob at {path}"
            raise E2eDecryptError(msg)
        if raw[0] != E2E_FORMAT_VERSION:
            msg = f"blob at {path} uses format {raw[0]}; update the app"
            raise E2eDecryptError(msg)
        if len(raw) < 1 + _NONCE + _TAG:
            msg = f"blob at {path} is truncated"
            raise E2eDecryptError(msg)
        try:
            clear = crypto_aead_xchacha20poly1305_ietf_decrypt(
                raw[1 + _NONCE :], _aad(raw[0], path), raw[1 : 1 + _NONCE], self._key
            )
        except CryptoError as exc:
            msg = f"blob at {path} failed authentication"
            raise E2eDecryptError(msg) from exc
        return clear.decode()


def is_e2e_envelope(text: str) -> bool:
    """Return whether ``text`` is an envelope (integer ``"v"``)."""
    try:
        data = json.loads(text)
    except ValueError:
        return False
    version = data.get("v") if isinstance(data, dict) else None
    return isinstance(version, int) and not isinstance(version, bool)


def _record_aad(
    path: str, rid: str, deleted: object, deleted_hlc: object, newest: object
) -> str:
    flag = 1 if deleted is True else 0
    return f"{path}#{rid}#{flag}#{deleted_hlc or ''}#{newest or ''}"


def _as_log(text: str) -> dict[str, dict[str, object]] | None:
    try:
        raw = json.loads(text)
    except ValueError:
        return None
    if not isinstance(raw, dict):
        return None
    for rid, rec in raw.items():
        if not isinstance(rec, dict) or rec.get("id") != rid:
            return None
        if not isinstance(rec.get("fields"), dict):
            return None
    return cast("dict[str, dict[str, object]]", raw)


def _newest(fields: dict[str, list[object]]) -> str | None:
    clocks = [Hlc.from_str(str(pair[1])) for pair in fields.values()]
    return max(clocks).to_str() if clocks else None


def seal_log_text(text: str, cipher: E2eCipher, *, path: str) -> str:
    """Seal a log (``dump_log`` shape) as an envelope; anything else whole."""
    log = _as_log(text)
    if log is None:
        return json.dumps(
            {"v": E2E_FORMAT_VERSION, "b": cipher.seal(text, path=path)},
            separators=(",", ":"),
        )
    records: dict[str, object] = {}
    for rid, rec in log.items():
        fields = cast("dict[str, list[object]]", rec["fields"])
        deleted = rec.get("deleted") is True
        deleted_hlc = rec.get("deleted_hlc")
        newest = _newest(fields)
        records[rid] = {
            "d": deleted,
            "dh": deleted_hlc,
            "h": newest,
            "p": cipher.seal(
                json.dumps(fields, separators=(",", ":"), ensure_ascii=False),
                path=_record_aad(path, rid, deleted, deleted_hlc, newest),
            ),
        }
    return json.dumps(
        {"v": E2E_FORMAT_VERSION, "r": records},
        separators=(",", ":"),
        ensure_ascii=False,
    )


def open_log_text(text: str, cipher: E2eCipher, *, path: str) -> str:
    """Open an envelope back to the ``dump_log`` shape."""
    if not is_e2e_envelope(text):
        if cipher.accept_plaintext:
            return text
        msg = f"plaintext blob at {path} after migration"
        raise E2eDecryptError(msg)
    data = json.loads(text)
    if data["v"] != E2E_FORMAT_VERSION:
        msg = f"blob at {path} uses format {data['v']}; update the app"
        raise E2eDecryptError(msg)
    whole = data.get("b")
    if isinstance(whole, str):
        return cipher.open(whole, path=path)
    records = data.get("r")
    if not isinstance(records, dict):
        msg = f"envelope at {path} is mis-shaped"
        raise E2eDecryptError(msg)
    out: dict[str, object] = {}
    for rid, rec in records.items():
        if (
            not isinstance(rec, dict)
            or not isinstance(rec.get("p"), str)
            or not isinstance(rec.get("d"), bool)
        ):
            msg = f"record {rid} at {path} is mis-shaped"
            raise E2eDecryptError(msg)
        clear = cipher.open(
            rec["p"],
            path=_record_aad(path, rid, rec["d"], rec.get("dh"), rec.get("h")),
        )
        out[rid] = {
            "id": rid,
            "fields": json.loads(clear),
            "deleted": rec["d"],
            "deleted_hlc": rec.get("dh"),
        }
    return json.dumps(out, separators=(",", ":"), ensure_ascii=False)
