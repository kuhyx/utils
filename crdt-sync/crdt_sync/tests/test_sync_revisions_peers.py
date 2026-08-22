"""Tests for revision handling across peers.

Split from ``test_sync_revisions.py`` (250-line cap), which keeps revision
identity, state, and no-op push suppression.
"""

from __future__ import annotations

from crdt_sync import (
    Hlc,
    Log,
    LogCodec,
    MemorySyncStateStore,
    Record,
    RevisionTracking,
    SyncTarget,
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
