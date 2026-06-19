"""Tests for log_integrity HMAC signing and verification."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from gatelock.log_integrity import (
    compute_entry_hmac,
    generate_hmac_key,
    verify_entry_hmac,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestGenerateHmacKey:
    """Tests for generate_hmac_key."""

    def test_generates_and_writes_key(self, tmp_path: Path) -> None:
        """Generates a 32-byte key and writes it to the given file."""
        key_file = tmp_path / "subdir" / "hmac.key"

        result = generate_hmac_key(key_file)

        assert result is not None
        assert len(result) == 32
        assert key_file.read_bytes() == result

    def test_returns_none_on_write_failure(self, tmp_path: Path) -> None:
        """Returns None when the key file cannot be written."""
        key_file = tmp_path / "hmac.key"

        with patch.object(
            type(key_file.parent), "mkdir", side_effect=OSError("denied")
        ):
            result = generate_hmac_key(key_file)

        assert result is None

    def test_defaults_to_default_key_file_path(self) -> None:
        """Calling with no argument targets DEFAULT_HMAC_KEY_FILE."""
        with patch("gatelock.log_integrity.DEFAULT_HMAC_KEY_FILE") as mock_default:
            mock_default.parent.mkdir.side_effect = OSError("denied")
            result = generate_hmac_key()

        assert result is None
        mock_default.parent.mkdir.assert_called_once()


class TestComputeEntryHmac:
    """Tests for compute_entry_hmac."""

    def test_computes_hmac_for_entry(self, tmp_path: Path) -> None:
        """Produces the expected hex HMAC for a given key and entry."""
        key_file = tmp_path / "hmac.key"
        key = b"test_key_12345"
        key_file.write_bytes(key)
        entry: dict[str, object] = {
            "timestamp": "2025-01-01T00:00:00",
            "workout_data": {"type": "test"},
        }

        result = compute_entry_hmac(entry, key_file=key_file)

        assert result is not None
        payload = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        expected = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
        assert result == expected

    def test_returns_none_when_key_file_missing(self, tmp_path: Path) -> None:
        """Returns None when the key file does not exist."""
        key_file = tmp_path / "nonexistent.key"

        result = compute_entry_hmac({"data": "test"}, key_file=key_file)

        assert result is None

    def test_defaults_to_default_key_file_path(self, tmp_path: Path) -> None:
        """Calling with no key_file argument reads DEFAULT_HMAC_KEY_FILE."""
        key_file = tmp_path / "hmac.key"
        key_file.write_bytes(b"default-path-key")
        with patch("gatelock.log_integrity.DEFAULT_HMAC_KEY_FILE", key_file):
            result = compute_entry_hmac({"data": "test"})

        assert result is not None


class TestVerifyEntryHmac:
    """Tests for verify_entry_hmac."""

    def test_valid_hmac(self, tmp_path: Path) -> None:
        """Verification passes when the stored HMAC matches the recomputed one."""
        key_file = tmp_path / "hmac.key"
        key = b"verification_key"
        key_file.write_bytes(key)
        entry_data: dict[str, object] = {
            "timestamp": "2025-01-01",
            "workout_data": {"type": "test"},
        }
        payload = json.dumps(entry_data, sort_keys=True, separators=(",", ":"))
        correct_hmac = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
        entry: dict[str, object] = {**entry_data, "hmac": correct_hmac}

        assert verify_entry_hmac(entry, key_file=key_file) is True

    def test_invalid_hmac(self, tmp_path: Path) -> None:
        """Verification fails when the stored HMAC does not match."""
        key_file = tmp_path / "hmac.key"
        key_file.write_bytes(b"verification_key")
        entry: dict[str, object] = {
            "timestamp": "2025-01-01",
            "hmac": "wrong_hmac_value",
        }

        assert verify_entry_hmac(entry, key_file=key_file) is False

    def test_missing_hmac_field(self, tmp_path: Path) -> None:
        """Verification fails when the entry has no hmac field at all."""
        entry: dict[str, object] = {"timestamp": "2025-01-01"}

        assert verify_entry_hmac(entry, key_file=tmp_path / "hmac.key") is False

    def test_non_string_hmac_field(self, tmp_path: Path) -> None:
        """Verification fails when the hmac field is not a string."""
        entry: dict[str, object] = {"timestamp": "2025-01-01", "hmac": 12345}

        assert verify_entry_hmac(entry, key_file=tmp_path / "hmac.key") is False

    def test_missing_key_file(self, tmp_path: Path) -> None:
        """Verification fails when the key file does not exist."""
        key_file = tmp_path / "nonexistent.key"
        entry: dict[str, object] = {"timestamp": "2025-01-01", "hmac": "some_hmac"}

        assert verify_entry_hmac(entry, key_file=key_file) is False
