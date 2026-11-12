# Copyright (c) 2026 Krzysztof Rudnicki
"""A peer whose log cannot be decrypted is skipped, not fatal."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from crdt_sync import (
    E2eDecryptError,
    GitHubSyncClient,
    LogCodec,
    SyncTarget,
    dump_log,
    load_log,
    sync_log,
)

if TYPE_CHECKING:
    import pytest


def test_undecryptable_peer_is_skipped(caplog: pytest.LogCaptureFixture) -> None:
    client = MagicMock(spec=GitHubSyncClient)
    client.list_directory.return_value = ["phone"]
    client.get_file_text.side_effect = E2eDecryptError("wrong key")
    codec = LogCodec(encode=dump_log, decode=load_log, filename="log.json")
    with caplog.at_level(logging.WARNING):
        merged = sync_log(SyncTarget(client, "pc", "devices"), {}, codec)
    assert merged == {}
    assert "Undecryptable log from device 'phone'" in caplog.text
