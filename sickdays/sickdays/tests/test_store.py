# Copyright (c) 2026 Krzysztof Rudnicki
"""An unusable pool fails closed for readers, and refuses writers, loudly."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pytest

from sickdays._api import add_sick_day, import_legacy, is_sick_day, remove_sick_day
from sickdays._errors import UnreadablePoolError
from sickdays._store import read_pool, read_pool_strict

if TYPE_CHECKING:
    from pathlib import Path

TODAY = date(2026, 10, 16)

CORRUPT_PAYLOADS = (
    "{not json",
    "[1, 2, 3]",
    '{"2026-10-16": {"fields": 5}}',
    '{"2026-10-16": {"id": "2026-10-16", "fields": {}}}',
    (
        '{"2026-10-16": {"id": "x", "fields": {"state": ["sick", "nope"]}, '
        '"deleted": false}}'
    ),
)


@pytest.mark.parametrize("payload", CORRUPT_PAYLOADS)
def test_a_corrupt_pool_reads_as_not_sick_and_is_logged(
    payload: str, state_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (state_dir / "sick_days.json").write_text(payload, encoding="utf-8")
    with caplog.at_level("WARNING"):
        assert not is_sick_day(TODAY)
    assert "NOT a sick day" in caplog.text
    assert "corrupt" in caplog.text


def test_an_unreadable_pool_reads_as_not_sick_and_is_logged(
    state_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (state_dir / "sick_days.json").mkdir()
    with caplog.at_level("WARNING"):
        assert not is_sick_day(TODAY)
    assert "cannot be read" in caplog.text


def test_a_missing_pool_is_silent(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("DEBUG"):
        assert read_pool(tmp_path / "absent.json") == {}
    assert not caplog.text


def test_strict_reading_raises_instead(tmp_path: Path) -> None:
    target = tmp_path / "pool.json"
    target.write_text("{not json", encoding="utf-8")
    with pytest.raises(UnreadablePoolError, match="corrupt"):
        read_pool_strict(target)


def test_writers_refuse_rather_than_overwrite_a_corrupt_pool(state_dir: Path) -> None:
    pool = state_dir / "sick_days.json"
    pool.write_text("{not json", encoding="utf-8")
    with pytest.raises(UnreadablePoolError):
        add_sick_day(TODAY, now=TODAY)
    with pytest.raises(UnreadablePoolError):
        remove_sick_day(TODAY, now=TODAY)
    with pytest.raises(UnreadablePoolError):
        import_legacy([TODAY])
    assert pool.read_text(encoding="utf-8") == "{not json"


def test_a_non_utf8_pool_fails_closed_and_refuses_writers(
    state_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (state_dir / "sick_days.json").write_bytes(b"\xff\xfe\x00junk")
    with caplog.at_level("WARNING"):
        assert not is_sick_day(TODAY)
    assert "cannot be read" in caplog.text
    with pytest.raises(UnreadablePoolError):
        add_sick_day(TODAY, now=TODAY)
