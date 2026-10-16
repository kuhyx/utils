# Copyright (c) 2026 Krzysztof Rudnicki
"""Signing the audit trail, using nothing but the standard library.

The same scheme as freedays' ``_hmac`` (HMAC-SHA256 over compact, sorted-key
JSON), copied rather than imported: sickdays and freedays must never import
each other's internals, and ``gatelock.log_integrity`` -- where the scheme
came from -- imports ``tkinter`` through ``gatelock/__init__``, which would
make ``import sickdays`` fail on any machine without Tk.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

_KEY_BYTES = 32


def load_key(key_file: Path) -> bytes | None:
    """Return the key bytes at ``key_file``, or None if unreadable."""
    try:
        return key_file.read_bytes().strip()
    except OSError:
        _logger.warning("cannot read the sick-day signing key from %s", key_file)
        return None


def generate_key(key_file: Path) -> bytes | None:
    """Create a key at ``key_file`` with owner-only permissions.

    Returns:
        The new key bytes, or None if it could not be written.
    """
    key = secrets.token_bytes(_KEY_BYTES)
    try:
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_bytes(key)
        key_file.chmod(0o600)
    except OSError:
        _logger.warning("cannot write the sick-day signing key to %s", key_file)
        return None
    return key


def _payload(entry: dict[str, Any]) -> bytes:
    return json.dumps(entry, sort_keys=True, separators=(",", ":")).encode()


def sign(entry: dict[str, Any], *, key_file: Path) -> str | None:
    """Return the hex HMAC of ``entry``, or None when the key is unavailable.

    ``entry`` must not already contain a ``hmac`` field.
    """
    key = load_key(key_file)
    if key is None:
        return None
    return hmac.new(key, _payload(entry), hashlib.sha256).hexdigest()


def verify(entry: dict[str, Any], *, key_file: Path) -> bool:
    """Whether ``entry``'s stored ``hmac`` matches its contents.

    False when the field is missing or not a string, and when the key cannot
    be read -- "cannot check" and "does not match" are the same answer to the
    only question a caller asks, which is whether to trust the line.
    """
    stored = entry.get("hmac")
    if not isinstance(stored, str):
        return False
    key = load_key(key_file)
    if key is None:
        return False
    without = {name: value for name, value in entry.items() if name != "hmac"}
    expected = hmac.new(key, _payload(without), hashlib.sha256).hexdigest()
    return hmac.compare_digest(stored, expected)
