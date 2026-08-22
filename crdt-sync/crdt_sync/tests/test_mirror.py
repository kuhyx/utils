"""Tests for the dual-write client used during the GitHub -> Firebase cutover.

The asymmetry is the whole point and is what these assert: a primary failure
must fail the tick, a mirror failure must not, and reads must consult both so
a half-migrated app (one device moved, one not) still converges both ways.

Mirrors ``crdt_sync_dart``'s ``test/mirror_store_test.dart``.
"""

from __future__ import annotations

import pytest

from crdt_sync import (
    MirrorSyncClient,
    RemoteSyncError,
)
from crdt_sync.tests.conftest import FakeStore


def _mirror(
    *,
    primary_files: dict[str, str] | None = None,
    mirror_files: dict[str, str] | None = None,
    primary_failing: bool = False,
    mirror_failing: bool = False,
) -> tuple[MirrorSyncClient, FakeStore, FakeStore, list[str]]:
    primary = FakeStore(primary_files, failing=primary_failing)
    mirror = FakeStore(mirror_files, failing=mirror_failing)
    failures: list[str] = []
    client = MirrorSyncClient(
        primary,
        mirror,
        on_mirror_failure=lambda operation, _: failures.append(operation),
    )
    return client, primary, mirror, failures


class TestWrites:
    """Writes."""

    def test_go_to_both_backends(self) -> None:
        """Go to both backends."""
        client, primary, mirror, _ = _mirror()
        client.put_file_text("ns/pc/log.json", "{}", message="m")
        assert primary.writes == ["ns/pc/log.json"]
        assert mirror.writes == ["ns/pc/log.json"]

    def test_a_primary_failure_fails_the_tick(self) -> None:
        # Fail-closed: the primary is authoritative, so a sync that could not
        # write it must not be reported as successful.
        """A primary failure fails the tick."""
        client, _, _, _ = _mirror(primary_failing=True)
        with pytest.raises(RemoteSyncError):
            client.put_file_text("ns/pc/log.json", "{}", message="m")

    def test_a_mirror_failure_is_loud_but_survivable(self) -> None:
        """A mirror failure is loud but survivable."""
        client, primary, _, failures = _mirror(mirror_failing=True)
        client.put_file_text("ns/pc/log.json", "{}", message="m")
        assert primary.writes == ["ns/pc/log.json"]
        assert failures == ["put_file_text ns/pc/log.json"]

    def test_deletes_behave_the_same_way(self) -> None:
        """Deletes behave the same way."""
        client, primary, _, failures = _mirror(
            primary_files={"ns/pc/log.json": "{}"},
            mirror_files={"ns/pc/log.json": "{}"},
            mirror_failing=True,
        )
        client.delete_file("ns/pc/log.json")
        assert not primary.files
        assert failures == ["delete_file ns/pc/log.json"]

    def test_a_primary_delete_failure_fails_the_tick(self) -> None:
        """A primary delete failure fails the tick."""
        client, _, _, _ = _mirror(primary_failing=True)
        with pytest.raises(RemoteSyncError):
            client.delete_file("ns/pc/log.json")


class TestReads:
    """Reads."""

    def test_prefer_the_primary_when_it_has_the_file(self) -> None:
        """Prefer the primary when it has the file."""
        client, _, _, _ = _mirror(
            primary_files={"ns/pc/log.json": "from-primary"},
            mirror_files={"ns/pc/log.json": "from-mirror"},
        )
        assert client.get_file_text("ns/pc/log.json") == "from-primary"

    def test_fall_back_to_the_mirror_for_an_unmigrated_device(self) -> None:
        # Why reads are not primary-only: a migrated PC must still see an
        # un-migrated phone's writes, or convergence silently becomes
        # one-directional with no error raised.
        """Fall back to the mirror for an unmigrated device."""
        client, _, _, _ = _mirror(mirror_files={"ns/phone/log.json": "from-mirror"})
        assert client.get_file_text("ns/phone/log.json") == "from-mirror"

    def test_return_none_when_neither_backend_has_the_file(self) -> None:
        """Return none when neither backend has the file."""
        client, _, _, _ = _mirror()
        assert client.get_file_text("ns/nobody/log.json") is None

    def test_a_mirror_read_failure_degrades_to_the_primary(self) -> None:
        """A mirror read failure degrades to the primary."""
        client, _, _, failures = _mirror(mirror_failing=True)
        assert client.get_file_text("ns/pc/log.json") is None
        assert failures == ["get_file_text ns/pc/log.json"]

    def test_a_primary_read_failure_with_nothing_in_the_mirror_raises(
        self,
    ) -> None:
        # Named for what it actually exercises: the primary raises AND the
        # mirror does not hold the file, so neither side has an answer. A
        # primary failure alone no longer fails the read -- see
        # TestPrimaryReadFallback.
        """A primary read failure with nothing in the mirror raises."""
        client, _, _, _ = _mirror(primary_failing=True)
        with pytest.raises(RemoteSyncError):
            client.get_file_text("ns/pc/log.json")


class TestListDirectory:
    """List directory."""

    def test_unions_devices_from_both_backends(self) -> None:
        """Unions devices from both backends."""
        client, _, _, _ = _mirror(
            primary_files={"ns/pc/log.json": "{}"},
            mirror_files={"ns/phone/log.json": "{}"},
        )
        assert sorted(client.list_directory("ns")) == ["pc", "phone"]

    def test_does_not_duplicate_a_device_present_in_both(self) -> None:
        """Does not duplicate a device present in both."""
        client, _, _, _ = _mirror(
            primary_files={"ns/pc/log.json": "{}"},
            mirror_files={"ns/pc/log.json": "{}"},
        )
        assert client.list_directory("ns") == ["pc"]

    def test_a_mirror_failure_degrades_to_the_primary_list(self) -> None:
        """A mirror failure degrades to the primary list."""
        client, _, _, failures = _mirror(
            primary_files={"ns/pc/log.json": "{}"}, mirror_failing=True
        )
        assert client.list_directory("ns") == ["pc"]
        assert failures == ["list_directory ns"]

    def test_a_primary_failure_degrades_to_the_mirror_list(self) -> None:
        # READS are resilient on both sides: a Firebase outage must not hide
        # the mirror's devices. This used to raise, which made a primary
        # outage look like "no devices exist" -- the union read silently
        # degrading to nothing, precisely when the fallback was needed.
        """A primary failure degrades to the mirror list."""
        client, _, _, _ = _mirror(
            primary_failing=True, mirror_files={"ns/phone/log.json": "{}"}
        )
        assert client.list_directory("ns") == ["phone"]

    def test_both_backends_failing_raises(self) -> None:
        # With no answer from either side, fail closed: an empty list is
        # indistinguishable from "no devices", and callers act on that.
        """Both backends failing raises."""
        client, _, _, _ = _mirror(primary_failing=True, mirror_failing=True)
        with pytest.raises(RemoteSyncError):
            client.list_directory("ns")
