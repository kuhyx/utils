# Copyright (c) 2026 Krzysztof Rudnicki
"""Among a day's good progress rows the last in file order wins, as one pair."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest

from earned_time import (
    LEETCODE,
    READING,
    WORKOUT,
    Progress,
    entry_signature,
    read_progress,
)
from earned_time.tests._maturity_rows import signed
from earned_time.tests._progress_rows import (
    DAY,
    bare,
    progress,
    tampered,
    write,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    Reader = Callable[..., Progress | None]


@pytest.fixture
def read(tmp_path: Path, key_file: Path) -> Reader:
    """Read LeetCode progress for ``DAY`` out of a ledger holding ``rows``."""

    def reader(rows: list[object]) -> Progress | None:
        ledger = write(tmp_path / "ledger.json", rows)
        return read_progress(LEETCODE, ledger, key_file, DAY)

    return reader


def test_a_later_row_with_a_lower_target_wins_whole(read: Reader) -> None:
    rows = [progress(done="1", target="5"), progress(done="2", target="3")]
    assert read(rows) == Progress(2, 3)


def test_a_later_row_with_a_lower_done_wins_whole(read: Reader) -> None:
    rows = [progress(done="2", target="3"), progress(done="1", target="3")]
    assert read(rows) == Progress(1, 3)


def test_a_later_row_with_a_higher_pair_wins_whole(read: Reader) -> None:
    rows = [progress(done="1", target="3"), progress(done="2", target="4")]
    assert read(rows) == Progress(2, 4)


def test_file_order_decides_not_the_numbers(read: Reader) -> None:
    rows = [progress(done="1", target="3"), progress(done="2", target="4")]
    assert read(rows[::-1]) == Progress(1, 3)


def test_the_last_row_of_three_wins(read: Reader) -> None:
    rows = [
        progress(done="3", target="3"),
        progress(done="1", target="6"),
        progress(done="2", target="6"),
    ]
    assert read(rows) == Progress(2, 6)


def test_a_trailing_forged_row_is_skipped(read: Reader) -> None:
    forged = tampered(progress(done="3", target="3"), done="2")
    assert read([progress(done="1", target="3"), forged]) == Progress(1, 3)


def test_a_trailing_row_with_the_wrong_key_is_skipped(read: Reader) -> None:
    row = progress(done="3", target="3")
    row["hmac"] = entry_signature(row, b"someone else")
    assert read([progress(done="1", target="3"), row]) == Progress(1, 3)


def test_a_trailing_unsigned_row_is_skipped(read: Reader) -> None:
    row = progress(done="3", target="3")
    del row["hmac"]
    assert read([progress(done="1", target="3"), row]) == Progress(1, 3)


@pytest.mark.parametrize("junk", ["garbage", 7, None, [], ["x"], {}, {"kind": 1}])
def test_a_trailing_garbage_entry_is_skipped(read: Reader, junk: object) -> None:
    assert read([progress(done="1", target="3"), junk]) == Progress(1, 3)


@pytest.mark.parametrize(
    "bad", [("x", "3"), ("1", "x"), ("1", "0"), ("", "3"), ("1", "9" * 5000)]
)
def test_a_trailing_unparsable_row_is_skipped(
    read: Reader, bad: tuple[str, str]
) -> None:
    rows = [progress(done="1", target="3"), progress(done=bad[0], target=bad[1])]
    assert read(rows) == Progress(1, 3)


def test_a_trailing_credit_row_is_skipped(read: Reader) -> None:
    credit = signed({**progress(done="3", target="3"), "kind": "credit"})
    assert read([progress(done="1", target="3"), credit]) == Progress(1, 3)


def test_trailing_rows_of_another_day_or_source_are_skipped(read: Reader) -> None:
    rows = [
        progress(done="1", target="3"),
        progress(done="3", target="3", day=DAY - timedelta(days=1)),
        progress(done="3", target="3", day=DAY + timedelta(days=1)),
        progress(done="3", target="3", source="reading"),
        progress(done="3", target="3", source="workout"),
    ]
    assert read(rows) == Progress(1, 3)


def test_a_malformed_detail_row_is_skipped(read: Reader) -> None:
    rows = [progress(done="1", target="3"), {**progress(), "detail": "x"}]
    assert read(rows) == Progress(1, 3)


def test_only_bad_rows_read_as_none(read: Reader) -> None:
    rows = [progress(done="x"), progress(source="reading"), "garbage"]
    assert read(rows) is None


def test_rows_without_created_at_and_device_are_accepted(
    tmp_path: Path, key_file: Path
) -> None:
    first, last = bare(done="1", target="3"), bare(done="2", target="3")
    assert "created_at" not in last
    assert "device" not in last
    ledger = write(tmp_path / "w.json", [first, last])
    assert read_progress(WORKOUT, ledger, key_file, DAY) == Progress(2, 3)


def test_the_rule_does_not_read_created_at(read: Reader) -> None:
    early = signed(
        {**bare(done="2", source="leetcode"), "created_at": "2026-11-24T23:00:00+00:00"}
    )
    late = signed(
        {**bare(done="1", source="leetcode"), "created_at": "2026-11-24T01:00:00+00:00"}
    )
    # File order, not timestamps: the later row in the file wins.
    assert read([early, late]) == Progress(1, 3)
    assert read([late, early]) == Progress(2, 3)


def test_each_source_reads_its_own_last_row(tmp_path: Path, key_file: Path) -> None:
    rows = [
        bare(done="1", target="3", source="workout"),
        progress(done="2", target="4", source="reading"),
        bare(done="3", target="3", source="workout"),
        progress(done="1", target="9", source="reading"),
    ]
    ledger = write(tmp_path / "mixed.json", rows)
    assert read_progress(WORKOUT, ledger, key_file, DAY) == Progress(3, 3)
    assert read_progress(READING, ledger, key_file, DAY) == Progress(1, 9)


def test_the_last_good_row_is_still_capped_at_its_target(read: Reader) -> None:
    rows = [progress(done="1", target="3"), progress(done="9", target="4")]
    assert read(rows) == Progress(4, 4)
