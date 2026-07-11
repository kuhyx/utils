"""Tests for local Log persistence (dump/load and atomic file read/write)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from crdt_sync import (
    Record,
    dump_log,
    load_log,
    read_log,
    write_log,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from crdt_sync import Hlc, Log


def _sample_log(make_hlc: Callable[..., Hlc]) -> Log:
    return {
        "a": Record(id="a", fields={"text": ("alpha", make_hlc(100))}),
        "b": Record(id="b", fields={}, deleted=True, deleted_hlc=make_hlc(200)),
    }


class TestDumpLoad:
    def test_round_trips_a_log(self, make_hlc: Callable[..., Hlc]) -> None:
        log = _sample_log(make_hlc)
        assert load_log(dump_log(log)) == log

    def test_load_raises_on_non_json(self) -> None:
        # json.loads raises JSONDecodeError (a ValueError subclass).
        with pytest.raises(json.JSONDecodeError):
            load_log("{not json")

    def test_load_raises_typeerror_on_wrong_shape(self) -> None:
        # Valid JSON, but a list where an id->record map is expected.
        with pytest.raises(TypeError):
            load_log("[]")


class TestReadWrite:
    def test_write_then_read_round_trips(
        self, tmp_path: Path, make_hlc: Callable[..., Hlc]
    ) -> None:
        log = _sample_log(make_hlc)
        path = tmp_path / "nested" / "log.json"
        write_log(path, log)
        assert read_log(path) == log

    def test_write_creates_parent_directories(
        self, tmp_path: Path, make_hlc: Callable[..., Hlc]
    ) -> None:
        path = tmp_path / "deep" / "nested" / "log.json"
        write_log(path, _sample_log(make_hlc))
        assert path.exists()

    def test_write_overwrites_atomically(
        self, tmp_path: Path, make_hlc: Callable[..., Hlc]
    ) -> None:
        path = tmp_path / "log.json"
        write_log(path, {"a": Record(id="a", fields={})})
        write_log(path, _sample_log(make_hlc))
        assert set(read_log(path)) == {"a", "b"}

    def test_read_of_missing_file_is_empty(self, tmp_path: Path) -> None:
        assert read_log(tmp_path / "nope.json") == {}

    def test_read_of_corrupt_file_is_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "log.json"
        path.write_text("{not json", encoding="utf-8")
        assert read_log(path) == {}

    def test_read_of_wrong_shape_file_is_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "log.json"
        path.write_text("[]", encoding="utf-8")
        assert read_log(path) == {}
