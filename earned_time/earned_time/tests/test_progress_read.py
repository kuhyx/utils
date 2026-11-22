# Copyright (c) 2026 Krzysztof Rudnicki
"""The progress reader: one signed fact, every other state is ``None``."""

from __future__ import annotations

from datetime import timedelta
from itertools import combinations
import logging
from typing import TYPE_CHECKING

import pytest

from earned_time import (
    LEETCODE,
    READING,
    REVIEW,
    TUTOR,
    WORKOUT,
    Earner,
    Progress,
    entry_signature,
    progress_map,
    read_progress,
)
from earned_time.tests._maturity_rows import KEY
from earned_time.tests._progress_rows import (
    DAY,
    home_ledger,
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

    def reader(rows: list[object], *, gate_off: bool = False) -> Progress | None:
        ledger = write(tmp_path / "ledger.json", rows)
        return read_progress(LEETCODE, ledger, key_file, DAY, gate_off=gate_off)

    return reader


def test_a_signed_matching_row_reads_as_progress(read: Reader) -> None:
    assert read([progress(done="1", target="3")]) == Progress(1, 3)


def test_no_row_reads_as_none(read: Reader) -> None:
    assert read([]) is None


def test_a_credit_row_is_not_progress(read: Reader) -> None:
    row = {**progress(), "kind": "credit"}
    assert read([{**row, "hmac": entry_signature(row, KEY)}]) is None


def test_a_wrong_day_row_reads_as_none(read: Reader) -> None:
    assert read([progress(day=DAY - timedelta(days=1))]) is None
    assert read([progress(day=DAY + timedelta(days=1))]) is None


def test_another_gates_source_reads_as_none(read: Reader) -> None:
    assert read([progress(source="reading")]) is None


def test_an_unsigned_row_reads_as_none(read: Reader) -> None:
    row = progress()
    del row["hmac"]
    assert read([row]) is None


def test_an_edited_row_reads_as_none(read: Reader) -> None:
    assert read([tampered(progress(done="1", target="3"), done="3")]) is None


def test_a_row_signed_with_another_key_reads_as_none(read: Reader) -> None:
    row = progress()
    row["hmac"] = entry_signature(row, b"someone else")
    assert read([row]) is None


ARABIC_ONE = chr(0x661)
ARABIC_THREE = chr(0x663)


@pytest.mark.parametrize(
    "bad",
    [1, 1.0, True, None, "", " 1", "1 ", "+1", "-1", "1.0", "1e1", "0x1", ARABIC_ONE],
)
def test_done_must_be_ascii_digits(read: Reader, bad: object) -> None:
    assert read([progress(done=bad, target="3")]) is None


@pytest.mark.parametrize(
    "bad",
    [3, 3.0, True, None, "", " 3", "3 ", "+3", "-3", "3.0", "0", "00", ARABIC_THREE],
)
def test_target_must_be_ascii_digits_and_positive(read: Reader, bad: object) -> None:
    assert read([progress(done="1", target=bad)]) is None


def test_absurdly_long_digit_strings_read_as_none(read: Reader) -> None:
    assert read([progress(done="1", target="9" * 5000)]) is None


def test_done_over_target_is_capped(read: Reader) -> None:
    assert read([progress(done="7", target="3")]) == Progress(3, 3)


def test_zero_done_is_a_valid_zero(read: Reader) -> None:
    assert read([progress(done="0", target="3")]) == Progress(0, 3)


def test_the_max_done_and_the_max_target_win(read: Reader) -> None:
    rows = [progress(done="1", target="3"), progress(done="2", target="4")]
    assert read(rows) == Progress(2, 4)
    assert read(rows[::-1]) == Progress(2, 4)


def test_a_bad_row_beside_a_good_one_is_ignored(read: Reader) -> None:
    rows = [progress(done="x", target="3"), progress(done="2", target="3")]
    assert read(rows) == Progress(2, 3)


def test_gate_off_ignores_progress(read: Reader) -> None:
    assert read([progress()], gate_off=True) is None
    assert read([progress()], gate_off=False) == Progress(1, 3)


def test_an_earner_without_a_progress_source_reads_as_none(
    tmp_path: Path, key_file: Path
) -> None:
    ledger = write(tmp_path / "t.json", [progress(source="tutor")])
    assert TUTOR.progress_source is None
    assert read_progress(TUTOR, ledger, key_file, DAY) is None


def test_every_gate_with_a_fact_names_its_source() -> None:
    sources = {e.name: e.progress_source for e in (WORKOUT, LEETCODE, READING, REVIEW)}
    assert sources == {
        "workout": "workout",
        "leetcode": "leetcode",
        "reading": "reading",
        "review": "review",
    }


def test_an_unreadable_key_reads_as_none_and_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    ledger = write(tmp_path / "ledger.json", [progress()])
    with caplog.at_level(logging.WARNING):
        assert read_progress(LEETCODE, ledger, tmp_path / "no.key", DAY) is None
    assert "integrity key" in caplog.text


def test_an_unreadable_ledger_reads_as_none_and_is_logged(
    tmp_path: Path, key_file: Path, caplog: pytest.LogCaptureFixture
) -> None:
    bad = tmp_path / "ledger.json"
    bad.write_text("not json", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert read_progress(LEETCODE, bad, key_file, DAY) is None
    assert "not valid JSON" in caplog.text


def test_a_missing_ledger_reads_as_none(tmp_path: Path, key_file: Path) -> None:
    assert read_progress(READING, tmp_path / "gone.json", key_file, DAY) is None


def test_deleting_rows_never_raises_the_share_at_one_target(read: Reader) -> None:
    rows: list[object] = [progress(done=str(n), target="5") for n in (0, 1, 2, 4, 5)]
    full = read(rows)
    assert full == Progress(5, 5)
    for size in range(len(rows) + 1):
        for kept in combinations(rows, size):
            got = read(list(kept))
            assert got is None or got.done <= full.done


def test_progress_map_holds_only_earners_with_a_fact(
    tmp_path: Path, key_file: Path
) -> None:
    write(
        home_ledger(tmp_path, WORKOUT),
        [progress(source="workout", done="1", target="2")],
    )
    write(home_ledger(tmp_path, LEETCODE), [progress(done="2", target="3")])
    found = progress_map(DAY, tmp_path, key_file)
    assert found == {"workout": Progress(1, 2), "leetcode": Progress(2, 3)}


def test_progress_map_skips_a_gate_that_is_off(tmp_path: Path, key_file: Path) -> None:
    write(home_ledger(tmp_path, LEETCODE), [progress()])
    assert progress_map(DAY, tmp_path, key_file, gate_off={"leetcode"}) == {}


def test_progress_map_over_an_explicit_registry(tmp_path: Path, key_file: Path) -> None:
    write(home_ledger(tmp_path, LEETCODE), [progress()])
    assert progress_map(DAY, tmp_path, key_file, earners=(WORKOUT,)) == {}
    assert progress_map(DAY, tmp_path, key_file, earners=(LEETCODE,)) == {
        "leetcode": Progress(1, 3)
    }


def test_a_row_without_a_detail_object_reads_as_none(read: Reader) -> None:
    for junk in (None, "x", ["done"]):
        row = {**progress(), "detail": junk}
        assert read([{**row, "hmac": entry_signature(row, KEY)}, 7, "x"]) is None


def test_progress_map_skips_an_earner_with_no_ledger(
    tmp_path: Path, key_file: Path
) -> None:
    bare = Earner(name="bare", label="bare", gaming_minutes=1, shutdown_minutes=1)
    assert progress_map(DAY, tmp_path, key_file, earners=(bare,)) == {}
