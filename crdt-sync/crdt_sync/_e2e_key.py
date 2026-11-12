# Copyright (c) 2026 Krzysztof Rudnicki
"""Argon2id key from the shared crdt-sync password, plus HKDF subkeys.

Byte-compatible with ``crdt_sync_dart``'s ``E2eKey``/``unlockE2e``: the clear
header at ``e2e_path`` holds salt, Argon2id cost and a check MAC, never a key.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import json
import secrets
from typing import TYPE_CHECKING

from argon2.low_level import Type, hash_secret_raw

from crdt_sync._e2e_cipher import E2eCipher

if TYPE_CHECKING:
    from crdt_sync._remote import RemoteStore

_SALT = 16
_MASTER = 32
_HEADER_VERSION = 1


@dataclass(frozen=True)
class Argon2Params:
    """Argon2id cost, stored in the header so it can be raised later."""

    memory_kib: int = 19456
    iterations: int = 2
    parallelism: int = 1


class E2eHeaderError(ValueError):
    """The header exists but cannot be parsed; it is never overwritten."""


class E2eWrongPassphraseError(Exception):
    """The passphrase does not match the header's check."""


def default_e2e_path(path_prefix: str) -> str:
    """Return the header path: a sibling of the device dirs, like ``revs``."""
    head, sep, _ = path_prefix.rpartition("/")
    return f"{head}/e2e" if sep else f"{path_prefix}/e2e"


def _hkdf(master: bytes, label: str) -> bytes:
    prk = hmac.new(b"", master, hashlib.sha256).digest()
    info = f"crdt_sync e2e {label}".encode()
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()


@dataclass(frozen=True)
class E2eKey:
    """A 32-byte master key and its subkeys. Never written to the remote."""

    master: bytes
    enc: bytes
    rev: bytes
    check: bytes

    @classmethod
    def from_bytes(cls, master: bytes) -> E2eKey:
        """Expand a cached 32-byte master key."""
        if len(master) != _MASTER:
            msg = "master key must be 32 bytes"
            raise ValueError(msg)
        return cls(
            master, _hkdf(master, "enc"), _hkdf(master, "rev"), _hkdf(master, "check")
        )

    def cipher(self, *, accept_plaintext: bool = True) -> E2eCipher:
        """Return the blob cipher for this key."""
        return E2eCipher(self.enc, accept_plaintext=accept_plaintext)

    def revision(self, text: str) -> str:
        """Return the keyed revision (hex HMAC-SHA256) of ``text``."""
        return hmac.new(self.rev, text.encode(), hashlib.sha256).hexdigest()

    def check_for(self, salt: bytes) -> str:
        """Return the header check value for ``salt``."""
        mac = hmac.new(self.check, salt, hashlib.sha256).digest()
        return base64.b64encode(mac).decode()


@dataclass(frozen=True)
class _Header:
    salt: bytes
    params: Argon2Params
    check: str

    @classmethod
    def parse(cls, text: str) -> _Header:
        try:
            data = json.loads(text)
        except ValueError as exc:
            msg = "e2e header is not JSON"
            raise E2eHeaderError(msg) from exc
        if not isinstance(data, dict) or data.get("v") != _HEADER_VERSION:
            msg = "e2e header is not a known version"
            raise E2eHeaderError(msg)
        if data.get("kdf") != "argon2id":
            msg = "e2e header is malformed"
            raise E2eHeaderError(msg)
        try:
            return cls(
                base64.b64decode(data["salt"]),
                Argon2Params(int(data["m"]), int(data["t"]), int(data["p"])),
                str(data["check"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            msg = "e2e header is malformed"
            raise E2eHeaderError(msg) from exc

    def encode(self) -> str:
        return json.dumps(
            {
                "v": _HEADER_VERSION,
                "kdf": "argon2id",
                "salt": base64.b64encode(self.salt).decode(),
                "m": self.params.memory_kib,
                "t": self.params.iterations,
                "p": self.params.parallelism,
                "check": self.check,
            },
            separators=(",", ":"),
        )


def derive_key(passphrase: str, salt: bytes, params: Argon2Params) -> E2eKey:
    """Run Argon2id (v1.3) and expand the subkeys."""
    master = hash_secret_raw(
        secret=passphrase.encode(),
        salt=salt,
        time_cost=params.iterations,
        memory_cost=params.memory_kib,
        parallelism=params.parallelism,
        hash_len=32,
        type=Type.ID,
    )
    return E2eKey.from_bytes(master)


def read_header(store: RemoteStore, path: str) -> _Header | None:
    """Return the parsed header at ``path``, or None when absent."""
    text = store.get_file_text(path)
    return None if text is None else _Header.parse(text)


def key_matches(key: E2eKey, store: RemoteStore, path: str) -> bool:
    """Return whether ``key`` matches the header at ``path``."""
    header = read_header(store, path)
    return header is not None and hmac.compare_digest(
        key.check_for(header.salt), header.check
    )


def unlock_e2e(
    store: RemoteStore,
    *,
    path_prefix: str,
    passphrase: str,
    params: Argon2Params | None = None,
    e2e_path: str | None = None,
) -> E2eKey:
    """Derive the key from ``passphrase``, creating the header on first use."""
    if not passphrase:
        msg = "passphrase must not be empty"
        raise ValueError(msg)
    path = e2e_path or default_e2e_path(path_prefix)
    header = read_header(store, path)
    if header is None:
        salt = secrets.token_bytes(_SALT)
        cost = params or Argon2Params()
        key = derive_key(passphrase, salt, cost)
        encoded = _Header(salt, cost, key.check_for(salt)).encode()
        store.put_file_text(path, encoded, message=path)
        stored = store.get_file_text(path) or encoded
        if stored == encoded:
            return key
        header = _Header.parse(stored)
    key = derive_key(passphrase, header.salt, header.params)
    if not hmac.compare_digest(key.check_for(header.salt), header.check):
        raise E2eWrongPassphraseError
    return key
