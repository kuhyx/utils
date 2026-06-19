"""HMAC-based integrity checking for signed state entries.

Ported from the byte-for-byte-duplicated copies in testsAndMisc's
``python_pkg/shared/log_integrity.py`` and screen-locker's
``_log_integrity.py``. ``DEFAULT_HMAC_KEY_FILE`` keeps the exact same literal
path both copies used -- changing it would invalidate every already-signed
entry in wake_alarm's, screen-locker's, and diet_guard's existing state files.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from pathlib import Path
import secrets

_logger = logging.getLogger(__name__)

# HMAC key for signing state entries (root-owned, 0600).
DEFAULT_HMAC_KEY_FILE = Path("/etc/workout-locker/hmac.key")


def _load_hmac_key(key_file: Path) -> bytes | None:
    """Load the HMAC key from ``key_file``.

    Returns the key bytes, or None if the file cannot be read.
    """
    try:
        return key_file.read_bytes().strip()
    except OSError:
        _logger.warning("Cannot read HMAC key from %s", key_file)
        return None


def generate_hmac_key(key_file: Path | None = None) -> bytes | None:
    """Generate a new HMAC key and write it to ``key_file``.

    The key file's parent must be writable (requires root or a setup script).

    Args:
        key_file: Where to write the new key. None (the default) targets the
            shared, root-owned key location all three lockers expect -- read
            fresh from :data:`DEFAULT_HMAC_KEY_FILE` on every call, so tests
            (or callers) can repoint it by patching that module attribute.

    Returns:
        The new key bytes, or None on failure.
    """
    target = key_file if key_file is not None else DEFAULT_HMAC_KEY_FILE
    key = secrets.token_bytes(32)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(key)
    except OSError:
        _logger.warning("Cannot write HMAC key to %s", target)
        return None
    return key


def compute_entry_hmac(
    entry_data: dict[str, object],
    *,
    key_file: Path | None = None,
) -> str | None:
    """Compute HMAC-SHA256 for a state entry.

    Args:
        entry_data: The entry dict (without the 'hmac' field).
        key_file: Where to read the signing key from. None (the default)
            reads :data:`DEFAULT_HMAC_KEY_FILE` fresh on every call.

    Returns:
        Hex-encoded HMAC string, or None if the key is unavailable.
    """
    target = key_file if key_file is not None else DEFAULT_HMAC_KEY_FILE
    key = _load_hmac_key(target)
    if key is None:
        return None
    payload = json.dumps(entry_data, sort_keys=True, separators=(",", ":"))
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()


def verify_entry_hmac(
    entry: dict[str, object],
    *,
    key_file: Path | None = None,
) -> bool:
    """Verify the HMAC signature of a state entry.

    Args:
        entry: The full entry dict, including the 'hmac' field.
        key_file: Where to read the signing key from. None (the default)
            reads :data:`DEFAULT_HMAC_KEY_FILE` fresh on every call.

    Returns:
        True if the HMAC is valid, False if invalid or the key is unavailable.
    """
    stored_hmac = entry.get("hmac")
    if not isinstance(stored_hmac, str):
        return False
    target = key_file if key_file is not None else DEFAULT_HMAC_KEY_FILE
    key = _load_hmac_key(target)
    if key is None:
        return False
    entry_without_hmac = {k: v for k, v in entry.items() if k != "hmac"}
    payload = json.dumps(entry_without_hmac, sort_keys=True, separators=(",", ":"))
    expected = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(stored_hmac, expected)
