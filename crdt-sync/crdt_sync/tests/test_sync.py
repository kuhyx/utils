"""Tests for the pull/merge/push sync orchestration."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from crdt_sync import (
    GitHubSyncClient,
    LogCodec,
    Record,
    SyncTarget,
    sync_log,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from crdt_sync import Hlc, Log


def _encode(log: Log) -> str:
    return json.dumps(
        {record_id: record.to_dict() for record_id, record in log.items()}
    )


def _decode(text: str) -> Log:
    return {
        record_id: Record.from_dict(data)
        for record_id, data in json.loads(text).items()
    }


def _mock_client(
    *,
    devices: tuple[str, ...] = (),
    files: dict[str, str] | None = None,
) -> MagicMock:
    """Build a mock ``GitHubSyncClient`` covering the methods sync_log calls."""
    client = MagicMock(spec=GitHubSyncClient)
    client.list_directory.return_value = list(devices)
    resolved_files = files or {}
    client.get_file_text.side_effect = resolved_files.get
    return client


class TestSyncLog:
    """Sync log."""

    def test_pushes_local_log_when_no_other_devices_have_synced(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        """Pushes local log when no other devices have synced."""
        local_log = {"a": Record(id="a", fields={"text": ("hello", make_hlc(100))})}
        client = _mock_client()

        merged = sync_log(
            SyncTarget(
                client=client,
                device_id="pc",
                path_prefix="devices",
            ),
            local_log,
            LogCodec(
                decode=_decode,
                encode=_encode,
            ),
        )

        assert merged == local_log
        client.put_file_text.assert_called_once()
        assert client.put_file_text.call_args.args[0] == "devices/pc/log.json"

    def test_skips_its_own_device_id_when_listing(self) -> None:
        """Skips its own device id when listing."""
        client = _mock_client(
            devices=("pc", "phone"), files={"devices/phone/log.json": "{}"}
        )

        sync_log(
            SyncTarget(
                client=client,
                device_id="pc",
                path_prefix="devices",
            ),
            {},
            LogCodec(
                decode=_decode,
                encode=_encode,
            ),
        )

        client.get_file_text.assert_called_once_with("devices/phone/log.json")

    def test_skips_its_legacy_device_id_as_well_as_its_current_one(self) -> None:
        """A migrated device must not re-merge its own pre-migration log.

        Without this the old path looks like a peer, so the device pulls
        back everything it pushed under its former id every single tick.
        """
        client = _mock_client(
            devices=("pc", "new-uuid", "phone"),
            files={"devices/phone/log.json": "{}"},
        )

        sync_log(
            SyncTarget(
                client=client,
                device_id="new-uuid",
                legacy_device_id="pc",
                path_prefix="devices",
            ),
            {},
            LogCodec(
                decode=_decode,
                encode=_encode,
            ),
        )

        client.get_file_text.assert_called_once_with("devices/phone/log.json")

    def test_pulls_the_old_path_when_no_legacy_id_is_declared(self) -> None:
        """Sanity check the previous test: absent the legacy id, it *is* pulled."""
        client = _mock_client(
            devices=("pc", "new-uuid"), files={"devices/pc/log.json": "{}"}
        )

        sync_log(
            SyncTarget(
                client=client,
                device_id="new-uuid",
                path_prefix="devices",
            ),
            {},
            LogCodec(
                decode=_decode,
                encode=_encode,
            ),
        )

        client.get_file_text.assert_called_once_with("devices/pc/log.json")

    def test_merges_in_a_remote_devices_entries(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        """Merges in a remote devices entries."""
        remote_log = {
            "b": Record(id="b", fields={"text": ("from phone", make_hlc(100))})
        }
        client = _mock_client(
            devices=("phone",),
            files={"devices/phone/log.json": _encode(remote_log)},
        )

        merged = sync_log(
            SyncTarget(
                client=client,
                device_id="pc",
                path_prefix="devices",
            ),
            {},
            LogCodec(
                decode=_decode,
                encode=_encode,
            ),
        )

        assert merged == remote_log

    def test_uses_a_custom_filename_and_commit_message(self) -> None:
        """Uses a custom filename and commit message."""
        client = _mock_client()

        sync_log(
            SyncTarget(
                client=client,
                device_id="pc",
                path_prefix="devices",
            ),
            {},
            LogCodec(
                commit_message="custom message",
                decode=_decode,
                encode=_encode,
                filename="notes.json",
            ),
        )

        client.put_file_text.assert_called_once_with(
            "devices/pc/notes.json",
            "{}",
            message="custom message",
        )
