# Copyright (c) 2026 Krzysztof Rudnicki
"""Sync: convergence across devices, and silence when the network is not there."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from crdt_sync import ConfigError, FirebaseAuthError, RemoteSyncError, dump_log
import pytest

from sickdays._api import add_sick_day, is_sick_day, load, remove_sick_day
from sickdays._paths import Paths
from sickdays._store import write_pool
from sickdays._sync import SyncUnavailableError, get_client, sync, sync_quietly

if TYPE_CHECKING:
    from pathlib import Path

TODAY = date(2026, 10, 16)
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
    add_sick_day(LATER, now=TODAY)
    remote = FakeRemote()
    sync(client=remote)
    assert any("sickdays-sync/devices/" in path for path in remote.files)


def test_a_peers_day_arrives_and_becomes_sick_locally(state_dir: Path) -> None:
    peer_log = {}
    # Build a peer's pushed log by marking into a separate pool file.
    add_sick_day(LATER, now=TODAY)
    peer_log = load()
    remote = FakeRemote(
        {"sickdays-sync/devices/other-device/sick_days.json": dump_log(peer_log)}
    )
    # Start over with an empty local pool, then pull.
    write_pool(Paths.under(state_dir).log, {})
    assert not is_sick_day(LATER)
    sync(client=remote)
    assert is_sick_day(LATER)


def test_syncing_twice_changes_nothing() -> None:
    add_sick_day(LATER, now=TODAY)
    remote = FakeRemote()
    first = sync(client=remote)
    second = sync(client=remote)
    assert first == second


def test_a_corrupt_peer_push_is_skipped_rather_than_fatal() -> None:
    add_sick_day(LATER, now=TODAY)
    remote = FakeRemote(
        {"sickdays-sync/devices/broken/sick_days.json": "{not json at all"}
    )
    sync(client=remote)
    assert is_sick_day(LATER)


def test_an_unreachable_remote_raises_sync_unavailable() -> None:
    with pytest.raises(SyncUnavailableError, match="could not reach"):
        sync(client=BrokenRemote())


def test_sync_quietly_reports_failure_without_raising(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def _refuse() -> None:
        msg = "not configured"
        raise SyncUnavailableError(msg)

    monkeypatch.setattr("sickdays._sync.get_client", _refuse)
    with caplog.at_level("DEBUG"):
        assert sync_quietly() is False
    assert "sync skipped" in caplog.text


def test_sync_quietly_reports_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sickdays._sync.get_client", FakeRemote)
    assert sync_quietly() is True


def test_an_unconfigured_machine_cannot_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    def _unconfigured(_app: str) -> None:
        msg = "no config file"
        raise ConfigError(msg)

    monkeypatch.setattr("sickdays._sync.firebase_client_for", _unconfigured)
    with pytest.raises(SyncUnavailableError, match="not configured"):
        get_client()


def test_a_rejected_credential_cannot_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    def _rejected(_app: str) -> None:
        msg = "bad password"
        raise FirebaseAuthError(msg)

    monkeypatch.setattr("sickdays._sync.firebase_client_for", _rejected)
    with pytest.raises(SyncUnavailableError, match="rejected"):
        get_client()


def test_the_configured_client_is_used_when_none_is_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote = FakeRemote()
    monkeypatch.setattr("sickdays._sync.firebase_client_for", lambda _app: remote)
    add_sick_day(LATER, now=TODAY)
    sync()
    assert remote.files


def test_the_pool_can_be_pointed_elsewhere_wholesale(tmp_path: Path) -> None:
    elsewhere = tmp_path / "other"
    elsewhere.mkdir()
    paths = Paths.under(elsewhere)
    add_sick_day(LATER, now=TODAY, paths=paths)
    sync(client=FakeRemote(), paths=paths)
    assert is_sick_day(LATER, log_path=paths.log)


def test_an_expired_credential_mid_sync_does_not_fail_the_timer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refresh token expiring during the tick, not at client construction."""

    class ExpiringRemote(FakeRemote):
        def list_directory(self, path: str) -> list[str]:
            msg = f"refresh token rejected while listing {path}"
            raise FirebaseAuthError(msg)

    monkeypatch.setattr(
        "sickdays._sync.firebase_client_for", lambda _app: ExpiringRemote()
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
        "sickdays._sync.firebase_client_for", lambda _app: BrokenRemote()
    )
    with caplog.at_level("ERROR"):
        assert sync_quietly() is False
    assert "failed unexpectedly" in caplog.text
    assert "RuntimeError" in caplog.text


def test_a_removal_on_one_device_reaches_the_other() -> None:
    """The point of the state flip: un-marking survives a merge."""
    remote = FakeRemote()
    add_sick_day(LATER, now=TODAY)
    sync(client=remote)
    pushed = next(iter(remote.files))
    # The peer pushed the same log; then this device removes the day.
    remote.files["sickdays-sync/devices/phone/sick_days.json"] = remote.files[pushed]
    remove_sick_day(LATER, now=TODAY)
    sync(client=remote)
    assert not is_sick_day(LATER)
