"""Tests for the peer files sync_log declines to merge.

Split from ``test_sync.py`` (250-line cap). A peer whose pushed file is
missing, corrupt or the wrong shape must be skipped rather than allowed to
fail the whole sync; these cover each of those, plus skipping our own device.
"""

from __future__ import annotations

import json
import logging
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
    import pytest

    from crdt_sync import Log


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


class TestSyncLogSkips:
    """Peer files that must be passed over rather than merged."""

    def test_skips_a_device_with_no_pushed_file_yet(self) -> None:
        """Skips a device with no pushed file yet."""
        client = _mock_client(devices=("phone",), files={})

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

        assert not merged

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

        assert not merged
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

        assert not merged
