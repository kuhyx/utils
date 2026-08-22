"""Tests for the revision tracking that keeps sync inside the free tier.

Two savings, both measured against the GitHub-backed history this replaces:
88.3% of pushes there were byte-identical no-ops, and every tick
re-downloaded every peer's whole log regardless of whether it had changed.
These tests assert on *request counts*, since that -- not the merge result --
is what the free-tier headroom depends on.

Mirrors ``crdt_sync_dart``'s ``test/sync_revisions_test.dart``.
"""

from __future__ import annotations

from crdt_sync import (
    Hlc,
    Log,
    LogCodec,
    MemorySyncStateStore,
    Record,
    RevisionTracking,
    SyncState,
    SyncTarget,
    default_revs_path,
    dump_log,
    load_log,
    revision_of,
    sync_log,
)
from crdt_sync.tests.conftest import FakeStore, FakeStoreWithoutBulkRead


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


class TestRevisionOf:
    """Revision of."""

    def test_is_stable_for_identical_content(self) -> None:
        """Is stable for identical content."""
        assert revision_of('{"a":1}') == revision_of('{"a":1}')

    def test_differs_for_different_content(self) -> None:
        """Differs for different content."""
        assert revision_of('{"a":1}') != revision_of('{"a":2}')


class TestDefaultRevsPath:
    """Default revs path."""

    def test_is_a_sibling_of_the_device_directory(self) -> None:
        """Is a sibling of the device directory."""
        assert default_revs_path("diet-guard-sync/devices") == ("diet-guard-sync/revs")
        assert default_revs_path("todo-sync/notes") == "todo-sync/revs"

    def test_falls_back_to_a_child_when_there_is_no_parent(self) -> None:
        """Falls back to a child when there is no parent."""
        assert default_revs_path("ns") == "ns/revs"


class TestSyncState:
    """Sync state."""

    def test_round_trips_through_json(self) -> None:
        """Round trips through JSON."""
        state = SyncState(pushed_rev="abc", peer_revs={"phone": "def"})
        assert SyncState.from_json(state.to_json()) == state

    def test_tolerates_a_missing_peer_map(self) -> None:
        """Tolerates a missing peer map."""
        assert not SyncState.from_json({}).peer_revs

    def test_drops_malformed_peer_entries(self) -> None:
        """Drops malformed peer entries."""
        state = SyncState.from_json({"peer_revs": {"phone": 42}})
        assert not state.peer_revs

    def test_ignores_a_non_dict_peer_map(self) -> None:
        """Ignores a non dict peer map."""
        assert not SyncState.from_json({"peer_revs": "nonsense"}).peer_revs

    def test_ignores_a_non_string_pushed_rev(self) -> None:
        """Ignores a non string pushed rev."""
        assert SyncState.from_json({"pushed_rev": 42}).pushed_rev is None


class TestNoOpPushSuppression:
    """No op push suppression."""

    def test_pushes_and_publishes_a_revision_on_the_first_tick(self) -> None:
        """Pushes and publishes a revision on the first tick."""
        remote = FakeRemote()
        _tick(remote, MemorySyncStateStore(), _log("a", "1"))
        assert remote.writes == ["ns/devices/pc/log.json", "ns/revs/pc"]

    def test_a_second_unchanged_tick_writes_nothing(self) -> None:
        """A second unchanged tick writes nothing."""
        remote = FakeRemote()
        store = MemorySyncStateStore()
        local = _log("a", "1")
        _tick(remote, store, local)
        remote.writes.clear()
        _tick(remote, store, local)
        # This is the 88.3% of the old history that was pure waste.
        assert not remote.writes

    def test_a_changed_log_pushes_again(self) -> None:
        """A changed log pushes again."""
        remote = FakeRemote()
        store = MemorySyncStateStore()
        _tick(remote, store, _log("a", "1"))
        remote.writes.clear()
        _tick(remote, store, _log("a", "2"))
        assert "ns/devices/pc/log.json" in remote.writes

    def test_without_a_state_store_every_tick_pushes(self) -> None:
        """Without a state store every tick pushes."""
        remote = FakeRemote()
        local = _log("a", "1")
        _tick(remote, None, local)
        _tick(remote, None, local)
        assert remote.writes == ["ns/devices/pc/log.json"] * 2
        assert not [w for w in remote.writes if w.startswith("ns/revs")]
