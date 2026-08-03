"""Tests for the dual-write client used during the GitHub -> Firebase cutover.

The asymmetry is the whole point and is what these assert: a primary failure
must fail the tick, a mirror failure must not, and reads must consult both so
a half-migrated app (one device moved, one not) still converges both ways.

Mirrors ``crdt_sync_dart``'s ``test/mirror_store_test.dart``.
"""

from __future__ import annotations

import pytest

from crdt_sync import (
    Hlc,
    Log,
    MirrorSyncClient,
    Record,
    RemoteStore,
    RemoteSyncError,
    dump_log,
    load_log,
    sync_log,
)


class FakeStore:
    """A scriptable in-memory store that can be told to fail."""

    def __init__(
        self,
        files: dict[str, str] | None = None,
        *,
        failing: bool = False,
    ) -> None:
        """Start holding ``files``, failing every call if ``failing``."""
        self.files = dict(files or {})
        self.failing = failing
        self.writes: list[str] = []

    def _guard(self, what: str) -> None:
        if self.failing:
            msg = f"{what} failed"
            raise RemoteSyncError(msg)

    def list_directory(self, path: str) -> list[str]:
        """Return the distinct first segments under ``path``."""
        self._guard("list")
        prefix = f"{path}/"
        return sorted(
            {
                key[len(prefix) :].split("/")[0]
                for key in self.files
                if key.startswith(prefix)
            }
        )

    def get_file_text(self, path: str) -> str | None:
        """Return the stored text, if any."""
        self._guard("read")
        return self.files.get(path)

    def put_file_text(self, path: str, text: str, *, message: str) -> None:
        """Store ``text`` at ``path``."""
        del message
        self._guard("write")
        self.writes.append(path)
        self.files[path] = text

    def get_string_map(self, path: str) -> dict[str, str]:
        """Return the direct children of ``path`` as a flat map."""
        self._guard("map read")
        prefix = f"{path}/"
        return {
            key[len(prefix) :]: value
            for key, value in self.files.items()
            if key.startswith(prefix)
        }

    def delete_file(self, path: str, *, message: str = "") -> None:
        """Remove ``path`` if present."""
        del message
        self._guard("delete")
        self.files.pop(path, None)

    def can_access_remote(self) -> bool:
        """Return whether this backend is currently healthy."""
        return not self.failing


class FakeStoreWithoutBulkRead:
    """A store with no bulk-map read, standing in for GitHub.

    Composes rather than subclasses :class:`FakeStore`, because a subclass
    would inherit ``get_string_map`` -- the capability this fake must lack.
    """

    def __init__(self, files: dict[str, str] | None = None) -> None:
        """Wrap a plain :class:`FakeStore` holding ``files``."""
        self._inner = FakeStore(files)

    @property
    def files(self) -> dict[str, str]:
        """The wrapped store's contents."""
        return self._inner.files

    def list_directory(self, path: str) -> list[str]:
        """Delegate to the wrapped store."""
        return self._inner.list_directory(path)

    def get_file_text(self, path: str) -> str | None:
        """Delegate to the wrapped store."""
        return self._inner.get_file_text(path)

    def put_file_text(self, path: str, text: str, *, message: str) -> None:
        """Delegate to the wrapped store."""
        self._inner.put_file_text(path, text, message=message)

    def delete_file(self, path: str, *, message: str = "") -> None:
        """Delegate to the wrapped store."""
        self._inner.delete_file(path, message=message)

    def can_access_remote(self) -> bool:
        """Delegate to the wrapped store."""
        return self._inner.can_access_remote()


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
    def test_go_to_both_backends(self) -> None:
        client, primary, mirror, _ = _mirror()
        client.put_file_text("ns/pc/log.json", "{}", message="m")
        assert primary.writes == ["ns/pc/log.json"]
        assert mirror.writes == ["ns/pc/log.json"]

    def test_a_primary_failure_fails_the_tick(self) -> None:
        # Fail-closed: the primary is authoritative, so a sync that could not
        # write it must not be reported as successful.
        client, _, _, _ = _mirror(primary_failing=True)
        with pytest.raises(RemoteSyncError):
            client.put_file_text("ns/pc/log.json", "{}", message="m")

    def test_a_mirror_failure_is_loud_but_survivable(self) -> None:
        client, primary, _, failures = _mirror(mirror_failing=True)
        client.put_file_text("ns/pc/log.json", "{}", message="m")
        assert primary.writes == ["ns/pc/log.json"]
        assert failures == ["put_file_text ns/pc/log.json"]

    def test_deletes_behave_the_same_way(self) -> None:
        client, primary, _, failures = _mirror(
            primary_files={"ns/pc/log.json": "{}"},
            mirror_files={"ns/pc/log.json": "{}"},
            mirror_failing=True,
        )
        client.delete_file("ns/pc/log.json")
        assert not primary.files
        assert failures == ["delete_file ns/pc/log.json"]

    def test_a_primary_delete_failure_fails_the_tick(self) -> None:
        client, _, _, _ = _mirror(primary_failing=True)
        with pytest.raises(RemoteSyncError):
            client.delete_file("ns/pc/log.json")


class TestReads:
    def test_prefer_the_primary_when_it_has_the_file(self) -> None:
        client, _, _, _ = _mirror(
            primary_files={"ns/pc/log.json": "from-primary"},
            mirror_files={"ns/pc/log.json": "from-mirror"},
        )
        assert client.get_file_text("ns/pc/log.json") == "from-primary"

    def test_fall_back_to_the_mirror_for_an_unmigrated_device(self) -> None:
        # Why reads are not primary-only: a migrated PC must still see an
        # un-migrated phone's writes, or convergence silently becomes
        # one-directional with no error raised.
        client, _, _, _ = _mirror(mirror_files={"ns/phone/log.json": "from-mirror"})
        assert client.get_file_text("ns/phone/log.json") == "from-mirror"

    def test_return_none_when_neither_backend_has_the_file(self) -> None:
        client, _, _, _ = _mirror()
        assert client.get_file_text("ns/nobody/log.json") is None

    def test_a_mirror_read_failure_degrades_to_the_primary(self) -> None:
        client, _, _, failures = _mirror(mirror_failing=True)
        assert client.get_file_text("ns/pc/log.json") is None
        assert failures == ["get_file_text ns/pc/log.json"]

    def test_a_primary_read_failure_fails_the_tick(self) -> None:
        client, _, _, _ = _mirror(primary_failing=True)
        with pytest.raises(RemoteSyncError):
            client.get_file_text("ns/pc/log.json")


class TestListDirectory:
    def test_unions_devices_from_both_backends(self) -> None:
        client, _, _, _ = _mirror(
            primary_files={"ns/pc/log.json": "{}"},
            mirror_files={"ns/phone/log.json": "{}"},
        )
        assert sorted(client.list_directory("ns")) == ["pc", "phone"]

    def test_does_not_duplicate_a_device_present_in_both(self) -> None:
        client, _, _, _ = _mirror(
            primary_files={"ns/pc/log.json": "{}"},
            mirror_files={"ns/pc/log.json": "{}"},
        )
        assert client.list_directory("ns") == ["pc"]

    def test_a_mirror_failure_degrades_to_the_primary_list(self) -> None:
        client, _, _, failures = _mirror(
            primary_files={"ns/pc/log.json": "{}"}, mirror_failing=True
        )
        assert client.list_directory("ns") == ["pc"]
        assert failures == ["list_directory ns"]

    def test_a_primary_failure_fails_the_tick(self) -> None:
        client, _, _, _ = _mirror(primary_failing=True)
        with pytest.raises(RemoteSyncError):
            client.list_directory("ns")


class TestRevisionMaps:
    def test_merge_both_backends_with_the_primary_winning(self) -> None:
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
        client, _, _, failures = _mirror(
            primary_files={"ns/revs/pc": "primary-rev"}, mirror_failing=True
        )
        assert client.get_string_map("ns/revs") == {"pc": "primary-rev"}
        assert failures == ["get_string_map ns/revs"]

    def test_a_backend_without_bulk_reads_contributes_nothing(self) -> None:
        client = MirrorSyncClient(
            FakeStore({"ns/revs/pc": "primary-rev"}),
            FakeStoreWithoutBulkRead({"ns/revs/phone": "ignored"}),
        )
        assert client.get_string_map("ns/revs") == {"pc": "primary-rev"}

    def test_is_empty_when_neither_backend_has_bulk_reads(self) -> None:
        client = MirrorSyncClient(
            FakeStoreWithoutBulkRead(), FakeStoreWithoutBulkRead()
        )
        assert not client.get_string_map("ns/revs")


class TestLifecycle:
    def test_can_access_remote_reports_only_the_primary(self) -> None:
        # A Test-connection button must not report success because the
        # backend being retired happens to answer.
        broken, _, _, _ = _mirror(primary_failing=True)
        assert broken.can_access_remote() is False
        healthy, _, _, _ = _mirror(mirror_failing=True)
        assert healthy.can_access_remote() is True

    def test_a_mirror_failure_with_no_handler_is_logged_not_raised(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        client = MirrorSyncClient(FakeStore(), FakeStore(failing=True))
        client.put_file_text("ns/pc/log.json", "{}", message="m")
        assert "Mirror backend failed" in caplog.text

    def test_satisfies_the_remote_store_contract(self) -> None:
        client, _, _, _ = _mirror()
        assert isinstance(client, RemoteStore)


class TestEndToEndThroughSyncLog:
    def test_a_half_migrated_pair_still_converges_both_ways(self) -> None:
        # phone has not migrated and still writes only to GitHub; pc is on
        # Firebase with the GitHub mirror. Both must see both records.
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
            client=github,
            device_id="phone",
            path_prefix="ns/devices",
            local_log=log("from-phone", "node-phone"),
            encode=dump_log,
            decode=load_log,
        )
        merged = sync_log(
            client=MirrorSyncClient(firebase, github),
            device_id="pc",
            path_prefix="ns/devices",
            local_log=log("from-pc", "node-pc"),
            encode=dump_log,
            decode=load_log,
        )
        assert {"from-phone", "from-pc"} <= set(merged)
        # The pc's merged result is mirrored back to GitHub, so the
        # un-migrated phone sees it on its next tick.
        assert "ns/devices/pc/log.json" in github.files
