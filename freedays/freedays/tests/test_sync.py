"""Sync: convergence across devices, and silence when the network is not there."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from crdt_sync import ConfigError, FirebaseAuthError, RemoteSyncError, dump_log
import pytest

from freedays._api import is_free_day, load, mark
from freedays._paths import Paths
from freedays._sync import SyncUnavailableError, get_client, sync, sync_quietly

if TYPE_CHECKING:
    from pathlib import Path

TODAY = date(2026, 9, 7)
LATER = date(2026, 12, 24)


class FakeRemote:
    """An in-memory RemoteStore: a dict with the four methods sync calls."""

    def __init__(self, files: dict[str, str] | None = None) -> None:
        self.files: dict[str, str] = dict(files or {})

    def list_directory(self, path: str) -> list[str]:
        prefix = f"{path}/"
        return sorted(
            {
                name[len(prefix) :].split("/", 1)[0]
                for name in self.files
                if name.startswith(prefix)
            }
        )

    def get_file_text(self, path: str) -> str | None:
        return self.files.get(path)

    def put_file_text(self, path: str, text: str, *, message: str) -> None:
        del message
        self.files[path] = text

    def delete_file(self, path: str, *, message: str = "") -> None:
        del message
        self.files.pop(path, None)

    def can_access_remote(self) -> bool:
        return True


class BrokenRemote(FakeRemote):
    """A remote that fails the way an offline one does."""

    def list_directory(self, path: str) -> list[str]:
        msg = f"cannot reach {path}"
        raise RemoteSyncError(msg)


def test_a_local_day_is_pushed_to_the_remote() -> None:
    mark(LATER, now=TODAY)
    remote = FakeRemote()
    sync(client=remote)
    assert any("freedays-sync/devices/" in path for path in remote.files)


def test_a_peers_day_arrives_and_becomes_free_locally() -> None:
    peer_log = {}
    # Build a peer's pushed log by marking into a separate pool file.
    mark(LATER, now=TODAY)
    peer_log = load()
    remote = FakeRemote(
        {"freedays-sync/devices/other-device/free_days.json": dump_log(peer_log)}
    )
    # Start over with an empty local pool, then pull.
    from freedays._api import save

    save({})
    assert not is_free_day(LATER, now=TODAY)
    sync(client=remote)
    assert is_free_day(LATER, now=TODAY)


def test_syncing_twice_changes_nothing() -> None:
    mark(LATER, now=TODAY)
    remote = FakeRemote()
    first = sync(client=remote)
    second = sync(client=remote)
    assert first == second


def test_a_corrupt_peer_push_is_skipped_rather_than_fatal() -> None:
    mark(LATER, now=TODAY)
    remote = FakeRemote(
        {"freedays-sync/devices/broken/free_days.json": "{not json at all"}
    )
    sync(client=remote)
    assert is_free_day(LATER, now=TODAY)


def test_an_unreachable_remote_raises_sync_unavailable() -> None:
    with pytest.raises(SyncUnavailableError, match="could not reach"):
        sync(client=BrokenRemote())


def test_sync_quietly_reports_failure_without_raising(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def _refuse() -> None:
        msg = "not configured"
        raise SyncUnavailableError(msg)

    monkeypatch.setattr("freedays._sync.get_client", _refuse)
    with caplog.at_level("DEBUG"):
        assert sync_quietly() is False
    assert "sync skipped" in caplog.text


def test_sync_quietly_reports_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("freedays._sync.get_client", FakeRemote)
    assert sync_quietly() is True


def test_an_unconfigured_machine_cannot_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    def _unconfigured(_app: str) -> None:
        msg = "no config file"
        raise ConfigError(msg)

    monkeypatch.setattr("freedays._sync.firebase_client_for", _unconfigured)
    with pytest.raises(SyncUnavailableError, match="not configured"):
        get_client()


def test_a_rejected_credential_cannot_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    def _rejected(_app: str) -> None:
        msg = "bad password"
        raise FirebaseAuthError(msg)

    monkeypatch.setattr("freedays._sync.firebase_client_for", _rejected)
    with pytest.raises(SyncUnavailableError, match="rejected"):
        get_client()


def test_the_configured_client_is_used_when_none_is_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote = FakeRemote()
    monkeypatch.setattr("freedays._sync.firebase_client_for", lambda _app: remote)
    mark(LATER, now=TODAY)
    sync()
    assert remote.files


def test_the_pool_can_be_pointed_elsewhere_wholesale(tmp_path: Path) -> None:
    elsewhere = tmp_path / "other"
    elsewhere.mkdir()
    paths = Paths.under(elsewhere)
    mark(LATER, now=TODAY, paths=paths)
    sync(client=FakeRemote(), paths=paths)
    assert is_free_day(LATER, log_path=paths.log, now=TODAY)


def test_an_expired_credential_mid_sync_does_not_fail_the_timer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refresh token expiring during the tick, not at client construction."""

    class ExpiringRemote(FakeRemote):
        def list_directory(self, path: str) -> list[str]:
            msg = f"refresh token rejected while listing {path}"
            raise FirebaseAuthError(msg)

    monkeypatch.setattr(
        "freedays._sync.firebase_client_for", lambda _app: ExpiringRemote()
    )
    assert sync_quietly() is False


def test_an_unexpected_error_is_logged_with_a_traceback_and_swallowed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The contract is "never fail", and it must not hold only by coincidence.

    FirebaseAuthError happens to subclass RemoteSyncError today. Something
    that does not -- a bug, a changed upstream hierarchy -- must still leave
    the timer green rather than turning it red every 15 minutes.
    """

    class BrokenRemote(FakeRemote):
        def list_directory(self, path: str) -> list[str]:
            msg = f"something nobody predicted, at {path}"
            raise RuntimeError(msg)

    monkeypatch.setattr(
        "freedays._sync.firebase_client_for", lambda _app: BrokenRemote()
    )
    with caplog.at_level("ERROR"):
        assert sync_quietly() is False
    assert "failed unexpectedly" in caplog.text
    assert "RuntimeError" in caplog.text
