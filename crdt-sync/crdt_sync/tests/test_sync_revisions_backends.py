"""Tests for backends without bulk map reads, and publishing order.

Split from ``test_sync_revisions.py`` (250-line cap);
``test_sync_revisions_peers.py`` keeps peer-download suppression.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from crdt_sync import (
    FileSyncStateStore,
    Hlc,
    Log,
    LogCodec,
    MemorySyncStateStore,
    Record,
    RevisionTracking,
    SyncState,
    SyncTarget,
    dump_log,
    load_log,
    sync_log,
)
from crdt_sync.tests.conftest import FakeStore, FakeStoreWithoutBulkRead

if TYPE_CHECKING:
    from pathlib import Path


def _log(record_id: str, value: str, node_id: str = "node-a") -> Log:
    return {
        record_id: Record(
            id=record_id,
            fields={
                "value": (value, Hlc(wall_time_ms=1000, counter=0, node_id=node_id))
            },
        )
    }


# The library's own serialization, so these tests exercise the same encoding
# the apps use rather than a test-only one.
_encode = dump_log
_decode = load_log


FakeRemote = FakeStore
FakeRemoteWithoutBulkRead = FakeStoreWithoutBulkRead


def _tick(
    remote: FakeRemote,
    store: object = None,
    local: Log | None = None,
    device_id: str = "pc",
) -> Log:
    return sync_log(
        SyncTarget(
            client=remote,
            device_id=device_id,
            path_prefix="ns/devices",
        ),
        local or {},
        LogCodec(
            decode=_decode,
            encode=_encode,
        ),
        RevisionTracking(
            state_store=store,
        ),
    )


class TestBackendsWithoutBulkMapReads:
    """Backends without bulk map reads."""

    def test_still_sync_correctly_just_without_the_saving(self) -> None:
        # GitHubSyncClient has no get_string_map, so revision lookup degrades
        # to "fetch everything" -- correctness must not depend on it.
        """Still sync correctly just without the saving."""
        peer = _encode(_log("b", "from-phone", "node-b"))
        remote = FakeRemoteWithoutBulkRead({"ns/devices/phone/log.json": peer})
        store = MemorySyncStateStore()
        first = _tick(remote, store)
        assert "b" in first
        remote.reads.clear()
        _tick(remote, store, first)
        assert "ns/devices/phone/log.json" in remote.reads


class TestRevisionPublishingOrder:
    """Revision publishing order."""

    def test_publishes_the_log_before_its_revision(self) -> None:
        # Reversed, a peer would cache "seen rev X" against a log it never
        # received, and skip it forever.
        """Publishes the log before its revision."""
        remote = FakeRemote()
        _tick(remote, MemorySyncStateStore(), _log("a", "1"))
        assert remote.writes.index("ns/devices/pc/log.json") < remote.writes.index(
            "ns/revs/pc"
        )

    def test_each_device_writes_only_its_own_revision_key(self) -> None:
        # Per-device keys rather than one shared map: a whole-map write would
        # erase every other device's entry, after which those peers would look
        # permanently unchanged and never be fetched again.
        """Each device writes only its own revision key."""
        remote = FakeRemote({"ns/revs/phone": "peer-rev"})
        _tick(remote, MemorySyncStateStore(), _log("a", "1"))
        assert remote.files["ns/revs/phone"] == "peer-rev"

    def test_an_explicit_revs_path_overrides_the_default(self) -> None:
        """An explicit revs path overrides the default."""
        remote = FakeRemote()
        sync_log(
            SyncTarget(
                client=remote,
                device_id="pc",
                path_prefix="ns/devices",
            ),
            _log("a", "1"),
            LogCodec(
                decode=_decode,
                encode=_encode,
            ),
            RevisionTracking(
                revs_path="custom/place",
                state_store=MemorySyncStateStore(),
            ),
        )
        assert "custom/place/pc" in remote.writes


class TestTwoDevicesConverge:
    """Two devices converge."""

    def test_each_ends_up_with_the_others_records(self) -> None:
        """Each ends up with the others records."""
        remote = FakeRemote()
        pc_store, phone_store = MemorySyncStateStore(), MemorySyncStateStore()
        pc = _tick(remote, pc_store, _log("a", "from-pc", "node-pc"))
        phone = sync_log(
            SyncTarget(
                client=remote,
                device_id="phone",
                path_prefix="ns/devices",
            ),
            _log("b", "from-phone", "node-phone"),
            LogCodec(
                decode=_decode,
                encode=_encode,
            ),
            RevisionTracking(
                state_store=phone_store,
            ),
        )
        assert {"a", "b"} <= set(phone)
        pc_after = _tick(remote, pc_store, pc)
        assert {"a", "b"} <= set(pc_after)


class TestFileSyncStateStore:
    """File sync state store."""

    def test_round_trips_through_a_file(self, tmp_path: Path) -> None:
        """Round trips through a file."""
        store = FileSyncStateStore(tmp_path / "nested" / "state.json")
        state = SyncState(pushed_rev="abc", peer_revs={"phone": "def"})
        store.save(state)
        assert store.load() == state

    def test_load_returns_default_state_when_absent(self, tmp_path: Path) -> None:
        """Load returns default state when absent."""
        assert FileSyncStateStore(tmp_path / "missing.json").load() == SyncState()

    def test_load_returns_default_state_for_a_truncated_file(
        self, tmp_path: Path
    ) -> None:
        """Load returns default state for a truncated file."""
        path = tmp_path / "state.json"
        path.write_text('{"pushed_rev":', encoding="utf-8")
        assert FileSyncStateStore(path).load() == SyncState()

    def test_load_returns_default_state_for_a_non_dict_file(
        self, tmp_path: Path
    ) -> None:
        """Load returns default state for a non dict file."""
        path = tmp_path / "state.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        assert FileSyncStateStore(path).load() == SyncState()

    def test_survives_across_processes(self, tmp_path: Path) -> None:
        # The point of persisting at all: wake_alarm PC is a fresh process
        # every minute, so an in-memory store would save nothing.
        """Survives across processes."""
        path = tmp_path / "state.json"
        remote = FakeRemote()
        local = _log("a", "1")
        _tick(remote, FileSyncStateStore(path), local)
        remote.writes.clear()
        _tick(remote, FileSyncStateStore(path), local)
        assert not remote.writes


@pytest.mark.parametrize("device_id", ["pc", "phone"])
def test_a_device_publishes_its_revision_under_its_own_id(device_id: str) -> None:
    """A device publishes its revision under its own id."""
    remote = FakeRemote()
    _tick(remote, MemorySyncStateStore(), _log("a", "1"), device_id=device_id)
    assert f"ns/revs/{device_id}" in remote.writes
