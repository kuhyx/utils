"""Tests for the pull/merge/push sync orchestration."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from crdt_sync import GitHubSyncClient, Record, sync_log

if TYPE_CHECKING:
    from collections.abc import Callable

    import pytest

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
    def test_pushes_local_log_when_no_other_devices_have_synced(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        local_log = {"a": Record(id="a", fields={"text": ("hello", make_hlc(100))})}
        client = _mock_client()

        merged = sync_log(
            client=client,
            device_id="pc",
            path_prefix="devices",
            local_log=local_log,
            encode=_encode,
            decode=_decode,
        )

        assert merged == local_log
        client.put_file_text.assert_called_once()
        assert client.put_file_text.call_args.args[0] == "devices/pc/log.json"

    def test_skips_its_own_device_id_when_listing(self) -> None:
        client = _mock_client(
            devices=("pc", "phone"), files={"devices/phone/log.json": "{}"}
        )

        sync_log(
            client=client,
            device_id="pc",
            path_prefix="devices",
            local_log={},
            encode=_encode,
            decode=_decode,
        )

        client.get_file_text.assert_called_once_with("devices/phone/log.json")

    def test_skips_a_device_with_no_pushed_file_yet(self) -> None:
        client = _mock_client(devices=("phone",), files={})

        merged = sync_log(
            client=client,
            device_id="pc",
            path_prefix="devices",
            local_log={},
            encode=_encode,
            decode=_decode,
        )

        assert merged == {}

    def test_skips_a_device_whose_pushed_file_is_corrupt(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An interrupted/truncated push must not crash every other device's
        merge -- it is treated the same as a device that hasn't pushed yet.
        """
        client = _mock_client(
            devices=("phone",),
            files={"devices/phone/log.json": "{not valid json"},
        )

        with caplog.at_level(logging.WARNING):
            merged = sync_log(
                client=client,
                device_id="pc",
                path_prefix="devices",
                local_log={},
                encode=_encode,
                decode=_decode,
            )

        assert merged == {}
        assert "Unparsable log" in caplog.text

    def test_skips_a_device_whose_pushed_json_has_the_wrong_shape(self) -> None:
        """Valid JSON that isn't a record map (e.g. from an incompatible
        writer) must be skipped like corrupt JSON, not crash the whole
        sync -- this is what the broad ``(ValueError, KeyError, TypeError)``
        catch in ``_pull_remote_logs`` is for, not just JSON syntax errors.
        """
        client = _mock_client(
            devices=("phone",),
            files={"devices/phone/log.json": '{"a": 5}'},
        )

        merged = sync_log(
            client=client,
            device_id="pc",
            path_prefix="devices",
            local_log={},
            encode=_encode,
            decode=_decode,
        )

        assert merged == {}

    def test_merges_in_a_remote_devices_entries(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        remote_log = {
            "b": Record(id="b", fields={"text": ("from phone", make_hlc(100))})
        }
        client = _mock_client(
            devices=("phone",),
            files={"devices/phone/log.json": _encode(remote_log)},
        )

        merged = sync_log(
            client=client,
            device_id="pc",
            path_prefix="devices",
            local_log={},
            encode=_encode,
            decode=_decode,
        )

        assert merged == remote_log

    def test_uses_a_custom_filename_and_commit_message(self) -> None:
        client = _mock_client()

        sync_log(
            client=client,
            device_id="pc",
            path_prefix="devices",
            local_log={},
            encode=_encode,
            decode=_decode,
            filename="notes.json",
            commit_message="custom message",
        )

        client.put_file_text.assert_called_once_with(
            "devices/pc/notes.json",
            "{}",
            message="custom message",
        )
