"""Signing, and the ways it is allowed to fail."""

from __future__ import annotations

from typing import TYPE_CHECKING

from freedays._hmac import generate_key, load_key, sign, verify

if TYPE_CHECKING:
    from pathlib import Path

_ENTRY = {"action": "mark", "day": "2026-12-24", "actor": "device-1"}


def test_a_generated_key_is_owner_only(tmp_path: Path) -> None:
    """A signing key the rest of the machine can read is not much of one."""
    key_file = tmp_path / "hmac.key"
    generate_key(key_file)
    assert key_file.stat().st_mode & 0o077 == 0


def test_a_generated_key_round_trips(tmp_path: Path) -> None:
    key_file = tmp_path / "hmac.key"
    created = generate_key(key_file)
    assert created is not None
    assert load_key(key_file) == created


def test_two_generated_keys_differ(tmp_path: Path) -> None:
    first = generate_key(tmp_path / "a.key")
    second = generate_key(tmp_path / "b.key")
    assert first != second


def test_a_key_that_cannot_be_written_returns_none(tmp_path: Path) -> None:
    blocked = tmp_path / "a-file" / "hmac.key"
    blocked.parent.write_text("I am a file, not a directory", encoding="utf-8")
    assert generate_key(blocked) is None


def test_a_missing_key_reads_as_none(tmp_path: Path) -> None:
    assert load_key(tmp_path / "absent.key") is None


def test_signing_and_verifying_agree(tmp_path: Path) -> None:
    key_file = tmp_path / "hmac.key"
    generate_key(key_file)
    signature = sign(_ENTRY, key_file=key_file)
    assert signature is not None
    assert verify({**_ENTRY, "hmac": signature}, key_file=key_file)


def test_signing_is_stable_across_key_order(tmp_path: Path) -> None:
    """Sorted-key JSON: the same fields sign the same however they arrive."""
    key_file = tmp_path / "hmac.key"
    generate_key(key_file)
    reordered = dict(reversed(list(_ENTRY.items())))
    assert sign(_ENTRY, key_file=key_file) == sign(reordered, key_file=key_file)


def test_a_tampered_field_fails_verification(tmp_path: Path) -> None:
    key_file = tmp_path / "hmac.key"
    generate_key(key_file)
    signature = sign(_ENTRY, key_file=key_file)
    tampered = {**_ENTRY, "day": "2026-12-25", "hmac": signature}
    assert not verify(tampered, key_file=key_file)


def test_another_key_fails_verification(tmp_path: Path) -> None:
    mine = tmp_path / "mine.key"
    theirs = tmp_path / "theirs.key"
    generate_key(mine)
    generate_key(theirs)
    signature = sign(_ENTRY, key_file=mine)
    assert not verify({**_ENTRY, "hmac": signature}, key_file=theirs)


def test_an_entry_without_a_signature_does_not_verify(tmp_path: Path) -> None:
    key_file = tmp_path / "hmac.key"
    generate_key(key_file)
    assert not verify(dict(_ENTRY), key_file=key_file)


def test_a_non_string_signature_does_not_verify(tmp_path: Path) -> None:
    key_file = tmp_path / "hmac.key"
    generate_key(key_file)
    assert not verify({**_ENTRY, "hmac": 17}, key_file=key_file)


def test_verification_without_a_key_is_a_no(tmp_path: Path) -> None:
    """ "Cannot check" and "does not match" are the same answer to the caller."""
    assert not verify({**_ENTRY, "hmac": "deadbeef"}, key_file=tmp_path / "absent.key")


def test_signing_without_a_key_returns_none(tmp_path: Path) -> None:
    assert sign(_ENTRY, key_file=tmp_path / "absent.key") is None
