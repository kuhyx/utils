"""Tests for mirror fallback reads, revision maps and lifecycle.

Split from ``test_mirror.py`` (250-line cap), which keeps plain writes,
reads and directory listing.
"""

from __future__ import annotations

import pytest

from crdt_sync import (
    Hlc,
    Log,
    LogCodec,
    MirrorSyncClient,
    Record,
    RemoteStore,
    RemoteSyncError,
    SyncTarget,
    dump_log,
    load_log,
    sync_log,
)
from crdt_sync.tests.conftest import FakeStore, FakeStoreWithoutBulkRead


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


class TestPrimaryReadFallback:
    """A failing primary must never hide data the mirror can still serve."""

    def test_get_file_text_falls_back_to_the_mirror(self) -> None:
        """Get file text falls back to the mirror."""
        client, _, _, _ = _mirror(
            primary_failing=True, mirror_files={"ns/phone/log.json": "{}"}
        )
        assert client.get_file_text("ns/phone/log.json") == "{}"

    def test_get_file_text_raises_when_both_fail(self) -> None:
        """Get file text raises when both fail."""
        client, _, _, _ = _mirror(primary_failing=True, mirror_failing=True)
        with pytest.raises(RemoteSyncError):
            client.get_file_text("ns/phone/log.json")

    def test_get_file_text_raises_when_primary_fails_and_mirror_lacks_it(
        self,
    ) -> None:
        # A reachable mirror that simply does not hold the file is not an
        # answer either, since the primary's copy was never read.
        """Get file text raises when primary fails and mirror lacks it."""
        client, _, _, _ = _mirror(primary_failing=True)
        with pytest.raises(RemoteSyncError):
            client.get_file_text("ns/phone/log.json")

    def test_revision_map_falls_back_to_the_mirror(self) -> None:
        """Revision map falls back to the mirror."""
        client, _, _, _ = _mirror(
            primary_failing=True, mirror_files={"ns/revs/phone": "r1"}
        )
        assert client.get_string_map("ns/revs") == {"phone": "r1"}

    def test_revision_map_raises_when_both_fail(self) -> None:
        """Revision map raises when both fail."""
        client, _, _, _ = _mirror(primary_failing=True, mirror_failing=True)
        with pytest.raises(RemoteSyncError):
            client.get_string_map("ns/revs")

    def test_revision_map_tolerates_a_mirror_that_cannot_bulk_read(
        self,
    ) -> None:
        # A mirror with no bulk-read capability (GitHub) contributes nothing,
        # but that is not a failure -- it simply has no revisions to add, so a
        # working primary's map must still come back. Matches the Dart side,
        # where the capability check runs inside the guarded closure.
        """Revision map tolerates a mirror that cannot bulk read."""
        client = MirrorSyncClient(
            FakeStore({"ns/revs/pc": "r1"}),
            FakeStoreWithoutBulkRead(),
            on_mirror_failure=lambda *_: None,
        )
        assert client.get_string_map("ns/revs") == {"pc": "r1"}

    def test_writes_stay_fail_closed_on_a_primary_failure(self) -> None:
        # The read fix must NOT loosen writes: an unaccepted write has not
        # happened, so it must still fail the tick.
        """Writes stay fail closed on a primary failure."""
        client, _, _, _ = _mirror(primary_failing=True)
        with pytest.raises(RemoteSyncError):
            client.put_file_text("ns/pc/log.json", "{}", message="m")
        with pytest.raises(RemoteSyncError):
            client.delete_file("ns/pc/log.json")


class TestRevisionMaps:
    """Revision maps."""

    def test_merge_both_backends_with_the_primary_winning(self) -> None:
        """Merge both backends with the primary winning."""
        client, _, _, _ = _mirror(
            primary_files={"ns/revs/pc": "primary-rev"},
            mirror_files={"ns/revs/pc": "mirror-rev", "ns/revs/phone": "old"},
        )
        # An un-migrated device publishes revisions only to the mirror;
        # without this it would look revision-less and be re-downloaded
        # every tick for the whole trial.
        assert client.get_string_map("ns/revs") == {
            "pc": "primary-rev",
            "phone": "old",
        }

    def test_a_mirror_failure_degrades_to_primary_revisions(self) -> None:
        """A mirror failure degrades to primary revisions."""
        client, _, _, failures = _mirror(
            primary_files={"ns/revs/pc": "primary-rev"}, mirror_failing=True
        )
        assert client.get_string_map("ns/revs") == {"pc": "primary-rev"}
        assert failures == ["get_string_map ns/revs"]

    def test_a_backend_without_bulk_reads_contributes_nothing(self) -> None:
        """A backend without bulk reads contributes nothing."""
        client = MirrorSyncClient(
            FakeStore({"ns/revs/pc": "primary-rev"}),
            FakeStoreWithoutBulkRead({"ns/revs/phone": "ignored"}),
        )
        assert client.get_string_map("ns/revs") == {"pc": "primary-rev"}

    def test_is_empty_when_neither_backend_has_bulk_reads(self) -> None:
        """Is empty when neither backend has bulk reads."""
        client = MirrorSyncClient(
            FakeStoreWithoutBulkRead(), FakeStoreWithoutBulkRead()
        )
        assert not client.get_string_map("ns/revs")


class TestLifecycle:
    """Lifecycle."""

    def test_can_access_remote_reports_only_the_primary(self) -> None:
        # A Test-connection button must not report success because the
        # backend being retired happens to answer.
        """Can access remote reports only the primary."""
        broken, _, _, _ = _mirror(primary_failing=True)
        assert broken.can_access_remote() is False
        healthy, _, _, _ = _mirror(mirror_failing=True)
        assert healthy.can_access_remote() is True

    def test_a_mirror_failure_with_no_handler_is_logged_not_raised(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A mirror failure with no handler is logged not raised."""
        client = MirrorSyncClient(FakeStore(), FakeStore(failing=True))
        client.put_file_text("ns/pc/log.json", "{}", message="m")
        assert "Mirror backend failed" in caplog.text

    def test_satisfies_the_remote_store_contract(self) -> None:
        """Satisfies the remote store contract."""
        client, _, _, _ = _mirror()
        assert isinstance(client, RemoteStore)


class TestEndToEndThroughSyncLog:
    """End to end through sync log."""

    def test_a_half_migrated_pair_still_converges_both_ways(self) -> None:
        # phone has not migrated and still writes only to GitHub; pc is on
        # Firebase with the GitHub mirror. Both must see both records.
        """A half migrated pair still converges both ways."""
        github = FakeStore()
        firebase = FakeStore()

        def log(record_id: str, node_id: str) -> Log:
            return {
                record_id: Record(
                    id=record_id,
                    fields={
                        "v": (
                            record_id,
                            Hlc(wall_time_ms=1000, counter=0, node_id=node_id),
                        )
                    },
                )
            }

        sync_log(
            SyncTarget(
                client=github,
                device_id="phone",
                path_prefix="ns/devices",
            ),
            log("from-phone", "node-phone"),
            LogCodec(
                decode=load_log,
                encode=dump_log,
            ),
        )
        merged = sync_log(
            SyncTarget(
                client=MirrorSyncClient(firebase, github),
                device_id="pc",
                path_prefix="ns/devices",
            ),
            log("from-pc", "node-pc"),
            LogCodec(
                decode=load_log,
                encode=dump_log,
            ),
        )
        assert {"from-phone", "from-pc"} <= set(merged)
        # The pc's merged result is mirrored back to GitHub, so the
        # un-migrated phone sees it on its next tick.
        assert "ns/devices/pc/log.json" in github.files
