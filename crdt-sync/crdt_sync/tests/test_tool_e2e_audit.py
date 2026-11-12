# Copyright (c) 2026 Krzysztof Rudnicki
"""The RTDB plaintext audit behind the E2E done check."""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING

from crdt_sync import E2eCipher, seal_log_text
from tool import e2e_audit

if TYPE_CHECKING:
    import pytest

LOG = json.dumps(
    {
        "n": {
            "id": "n",
            "fields": {"title": ["x", "2026-01-01T00:00:00.000Z-0000-a"]},
            "deleted": False,
            "deleted_hlc": None,
        }
    }
)


def _sealed() -> str:
    return seal_log_text(LOG, E2eCipher(bytes(32)), path="a/devices-e2e/p/log.json")


def test_sealed_tree_is_clean() -> None:
    tree = {
        "devices-e2e": {"p": {"log~2Ejson": _sealed()}},
        "revs-e2e": {"p": "ab" * 32},
        "e2e": '{"v":1,"kdf":"argon2id"}',
    }
    assert e2e_audit.plaintext_paths(tree) == []


def test_plaintext_leaf_is_reported_with_decoded_key() -> None:
    tree = {"devices": {"p": {"log~2Ejson": LOG}}, "settings": {"k": '{"a":1}'}}
    assert e2e_audit.plaintext_paths(tree) == [
        "devices/p/log.json",
        "settings/k",
    ]


def test_raw_json_scalars_count_as_plaintext() -> None:
    assert e2e_audit.plaintext_paths({"a": 5, "b": True, "c": None}) == ["a", "b"]


def test_main_reads_stdin_and_sets_exit_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"x": LOG})))
    assert e2e_audit.main(["todo-sync"]) == 1
    assert "todo-sync/x" in capsys.readouterr().out
    monkeypatch.setattr("sys.stdin", io.StringIO("null"))
    assert e2e_audit.main(["todo-sync"]) == 0
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"x": _sealed()})))
    assert e2e_audit.main([]) == 0
