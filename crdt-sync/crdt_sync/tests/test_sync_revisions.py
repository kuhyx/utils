"""Tests for the revision tracking that keeps sync inside the free tier.

Two savings, both measured against the GitHub-backed history this replaces:
88.3% of pushes there were byte-identical no-ops, and every tick
re-downloaded every peer's whole log regardless of whether it had changed.
These tests assert on *request counts*, since that -- not the merge result --
is what the free-tier headroom depends on.

Mirrors ``crdt_sync_dart``'s ``test/sync_revisions_test.dart``.
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
    default_revs_path,
    dump_log,
    load_log,
    revision_of,
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


class TestPeerDownloadSuppression:
    """Peer download suppression."""

    def test_downloads_a_peer_whose_revision_it_has_never_seen(self) -> None:
        """Downloads a peer whose revision it has never seen."""
        peer = _encode(_log("b", "from-phone", "node-b"))
        remote = FakeRemote(
            {
                "ns/devices/phone/log.json": peer,
                "ns/revs/phone": revision_of(peer),
            }
        )
        merged = _tick(remote, MemorySyncStateStore())
        assert "ns/devices/phone/log.json" in remote.reads
        assert "b" in merged

    def test_skips_the_download_when_the_peer_revision_is_unchanged(self) -> None:
        """Skips the download when the peer revision is unchanged."""
        peer = _encode(_log("b", "from-phone", "node-b"))
        remote = FakeRemote(
            {
                "ns/devices/phone/log.json": peer,
                "ns/revs/phone": revision_of(peer),
            }
        )
        store = MemorySyncStateStore()
        first = _tick(remote, store)
        remote.reads.clear()
        # The peer's records are already in the local log from tick one, so
        # re-downloading is pure waste -- the ~700 MB/month this removes.
        _tick(remote, store, first)
        assert not remote.reads

    def test_downloads_again_once_the_peer_publishes_a_new_revision(self) -> None:
        """Downloads again once the peer publishes a new revision."""
        peer_v1 = _encode(_log("b", "v1", "node-b"))
        remote = FakeRemote(
            {
                "ns/devices/phone/log.json": peer_v1,
                "ns/revs/phone": revision_of(peer_v1),
            }
        )
        store = MemorySyncStateStore()
        first = _tick(remote, store)
        remote.reads.clear()

        peer_v2 = _encode({**_decode(peer_v1), **_log("c", "v2", "node-b")})
        remote.files["ns/devices/phone/log.json"] = peer_v2
        remote.files["ns/revs/phone"] = revision_of(peer_v2)

        second = _tick(remote, store, first)
        assert "ns/devices/phone/log.json" in remote.reads
        assert {"b", "c"} <= set(second)

    def test_re_downloads_a_peer_whose_push_was_corrupt(self) -> None:
        # A failed decode must not be remembered as seen, or the corruption
        # would be permanent.
        """Re downloads a peer whose push was corrupt."""
        remote = FakeRemote(
            {
                "ns/devices/phone/log.json": "not json at all",
                "ns/revs/phone": revision_of("not json at all"),
            }
        )
        store = MemorySyncStateStore()
        _tick(remote, store)
        remote.reads.clear()
        _tick(remote, store)
        assert "ns/devices/phone/log.json" in remote.reads

    def test_downloads_when_the_peer_has_published_no_revision(self) -> None:
        # A device still running pre-migration code publishes a log but no
        # revision; it must not be silently ignored.
        """Downloads when the peer has published no revision."""
        peer = _encode(_log("b", "from-phone", "node-b"))
        remote = FakeRemote({"ns/devices/phone/log.json": peer})
        assert "b" in _tick(remote, MemorySyncStateStore())

    def test_skips_a_peer_with_nothing_pushed_yet(self) -> None:
        """Skips a peer with nothing pushed yet."""
        remote = FakeRemote({"ns/devices/phone/other.txt": "x"})
        assert not _tick(remote, MemorySyncStateStore())

    def test_never_reads_its_own_device_back(self) -> None:
        """Never reads its own device back."""
        remote = FakeRemote(
            {
                "ns/devices/pc/log.json": _encode(_log("a", "1")),
                "ns/revs/pc": "whatever",
            }
        )
        _tick(remote, MemorySyncStateStore())
        assert not remote.reads


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
