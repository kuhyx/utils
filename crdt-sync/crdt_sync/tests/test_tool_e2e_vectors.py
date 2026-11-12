# Copyright (c) 2026 Krzysztof Rudnicki
"""tool/e2e_vectors writes vectors that Python itself can open."""

from __future__ import annotations

import json
from pathlib import Path
import runpy

import pytest

from crdt_sync import open_log_text, unlock_e2e
from crdt_sync.tests.conftest import FakeStore
from tool import e2e_vectors


def test_vectors_open_with_the_stated_passphrase() -> None:
    vec = e2e_vectors.vectors()
    key = unlock_e2e(
        FakeStore({"vec/e2e": str(vec["header"])}),
        path_prefix="vec/notes-e2e",
        passphrase=str(vec["passphrase"]),
        e2e_path="vec/e2e",
    )
    assert key.master.hex() == vec["master_hex"]
    path = str(vec["path"])
    opened = open_log_text(str(vec["envelope"]), key.cipher(), path=path)
    assert json.loads(opened) == json.loads(str(vec["log"]))
    assert open_log_text(str(vec["whole"]), key.cipher(), path=path) == "not a log"


def test_main_prints_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert e2e_vectors.main() == 0
    assert "master_hex" in json.loads(capsys.readouterr().out)


def test_module_entry_point(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(Path(e2e_vectors.__file__)), run_name="__main__")
    assert exc.value.code == 0
    assert "envelope" in capsys.readouterr().out
