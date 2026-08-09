"""Tests for this device's persisted sync identity."""

from __future__ import annotations

from typing import TYPE_CHECKING
import uuid

import pytest

from crdt_sync import DeviceIdentity, load_device_identity

if TYPE_CHECKING:
    from pathlib import Path


def test_mints_a_uuid_on_first_call(tmp_path: Path) -> None:
    """A device with no id file gets a fresh uuid4, persisted."""
    path = tmp_path / "device_id"

    identity = load_device_identity(path)

    assert uuid.UUID(identity.device_id).version == 4
    assert path.read_text(encoding="utf-8").strip() == identity.device_id


def test_returns_the_same_id_on_every_later_call(tmp_path: Path) -> None:
    """The id is stable across restarts -- that is the whole point."""
    path = tmp_path / "device_id"

    first = load_device_identity(path)
    second = load_device_identity(path)

    assert first.device_id == second.device_id


def test_creates_missing_parent_directories(tmp_path: Path) -> None:
    """First run on a clean machine has no state dir yet."""
    path = tmp_path / "nested" / "deeper" / "device_id"

    identity = load_device_identity(path)

    assert path.read_text(encoding="utf-8").strip() == identity.device_id


def test_treats_a_blank_file_as_absent(tmp_path: Path) -> None:
    """An empty/whitespace file (interrupted first write) re-mints."""
    path = tmp_path / "device_id"
    path.write_text("   \n", encoding="utf-8")

    identity = load_device_identity(path)

    assert uuid.UUID(identity.device_id).version == 4


def test_reads_an_id_that_is_not_a_uuid(tmp_path: Path) -> None:
    """Whatever is on disk wins; the file is the source of truth."""
    path = tmp_path / "device_id"
    path.write_text("hand-edited-id\n", encoding="utf-8")

    assert load_device_identity(path).device_id == "hand-edited-id"


def test_a_file_blocking_the_state_dir_surfaces_as_an_error(tmp_path: Path) -> None:
    """A file where the state directory belongs is a real misconfiguration.

    The read is tolerant (it reads as "no id yet"), but the subsequent mkdir
    must not be: silently continuing would hand back an id that was never
    persisted, so every restart would mint a new one and strand a device
    directory in the namespace each time.
    """
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory\n", encoding="utf-8")

    with pytest.raises((NotADirectoryError, FileExistsError)):
        load_device_identity(tmp_path / "blocker" / "device_id")


def test_legacy_id_is_carried_onto_the_identity(tmp_path: Path) -> None:
    """The pre-migration role constant travels with the new uuid."""
    identity = load_device_identity(tmp_path / "device_id", legacy_id="pc")

    assert identity.legacy_id == "pc"


def test_legacy_id_is_carried_when_loading_an_existing_id(tmp_path: Path) -> None:
    """The load branch carries it too, not just the mint branch."""
    path = tmp_path / "device_id"
    path.write_text("existing-uuid\n", encoding="utf-8")

    identity = load_device_identity(path, legacy_id="pc")

    assert (identity.device_id, identity.legacy_id) == ("existing-uuid", "pc")


def test_own_ids_includes_both_ids_when_migrating() -> None:
    """Skip-own must match the old path as well as the new one."""
    identity = DeviceIdentity(device_id="new-uuid", legacy_id="pc")

    assert identity.own_ids == frozenset({"new-uuid", "pc"})


def test_own_ids_is_just_the_uuid_once_the_old_path_is_reclaimed() -> None:
    """After GC there is no legacy id left to skip."""
    assert DeviceIdentity(device_id="new-uuid").own_ids == frozenset({"new-uuid"})


def test_is_own_matches_either_id() -> None:
    """Both the current and the former id mean "this device"."""
    identity = DeviceIdentity(device_id="new-uuid", legacy_id="pc")

    assert identity.is_own("new-uuid")
    assert identity.is_own("pc")
    assert not identity.is_own("phone")
