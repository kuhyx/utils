# Copyright (c) 2026 Krzysztof Rudnicki
"""Reading a day's keep set: each wire-format rule, pinned."""

from __future__ import annotations

from datetime import date
import logging
from typing import TYPE_CHECKING

from crdt_sync import Hlc, Record
import pytest

from sickdays._constants import LOCKERS
from sickdays._keep import (
    keep_wire,
    normalise_keep,
    read_keep,
    validate_locker,
    with_keep,
)
from sickdays._model import SickDay, build_record, record_hlc, to_sick_day

if TYPE_CHECKING:
    from typing import Any

DAY = date(2026, 10, 20)


def _tick(wall_ms: int, node: str = "pc") -> Hlc:
    return Hlc(wall_time_ms=wall_ms, counter=0, node_id=node)


def _sick(keep: tuple[Any, Hlc] | None, state_at: int = 5) -> Record:
    fields: dict[str, tuple[Any, Hlc]] = {
        "state": ("sick", _tick(state_at)),
        "actor": ("pc", _tick(state_at)),
    }
    if keep is not None:
        fields["keep"] = keep
    return Record(id="2026-10-20", fields=fields)


def test_a_0_1_0_record_without_keep_keeps_nothing() -> None:
    assert read_keep(_sick(None)) == frozenset()


def test_a_keep_older_than_state_is_stale() -> None:
    assert read_keep(_sick((["leetcode"], _tick(4)))) == frozenset()


def test_a_keep_from_the_same_tick_counts() -> None:
    assert read_keep(_sick((["leetcode"], _tick(5)))) == {"leetcode"}


def test_a_later_keep_counts() -> None:
    assert read_keep(_sick((["book", "diet"], _tick(9)))) == {"book", "diet"}


@pytest.mark.parametrize("value", ["leetcode", {"leetcode": True}, ["diet", 7], None])
def test_a_malformed_keep_fails_closed_to_every_locker(
    value: object, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        assert read_keep(_sick((value, _tick(5)))) == frozenset(LOCKERS)
    assert "malformed keep field" in caplog.text


def test_a_stale_malformed_keep_is_still_just_stale() -> None:
    assert read_keep(_sick(("junk", _tick(1)))) == frozenset()


def test_unknown_ids_are_ignored() -> None:
    record = _sick((["hologram", "leetcode"], _tick(5)))
    assert read_keep(record) == {"leetcode"}


def test_a_keep_without_a_state_is_read_as_is() -> None:
    record = Record(id="2026-10-20", fields={"keep": (["book"], _tick(1))})
    assert read_keep(record) == {"book"}


def test_validate_locker_names_the_choices() -> None:
    assert validate_locker("alarm") == "alarm"
    with pytest.raises(ValueError, match="workout, leetcode, book, diet, alarm"):
        validate_locker("leetcod")


def test_normalise_deduplicates_and_refuses_junk() -> None:
    assert normalise_keep(["diet", "diet", "book"]) == {"book", "diet"}
    assert normalise_keep(()) == frozenset()
    with pytest.raises(TypeError, match="not the string"):
        normalise_keep("diet")
    with pytest.raises(ValueError, match="unknown locker"):
        normalise_keep(["diet", "nope"])


def test_the_wire_value_is_sorted() -> None:
    assert keep_wire(frozenset({"workout", "alarm", "leetcode"})) == [
        "alarm",
        "leetcode",
        "workout",
    ]


def test_an_add_writes_keep_on_the_state_tick() -> None:
    entry = SickDay(DAY, is_sick=True, actor="pc", keep=frozenset({"diet", "book"}))
    record = build_record(entry, _tick(3))
    assert record.fields["keep"] == (["book", "diet"], _tick(3))
    assert record.fields["state"] == ("sick", _tick(3))
    assert to_sick_day(record) == entry


def test_a_clear_writes_an_empty_keep_on_the_state_tick() -> None:
    entry = SickDay(DAY, is_sick=False, actor="pc", keep=frozenset({"diet"}))
    record = build_record(entry, _tick(3))
    assert record.fields["keep"] == ([], _tick(3))
    assert to_sick_day(record) == SickDay(DAY, is_sick=False, actor="pc")


def test_with_keep_restamps_only_keep_and_actor() -> None:
    record = _sick((["book"], _tick(5)))
    edited = with_keep(record, frozenset({"alarm"}), actor="phone", tick=_tick(8))
    assert edited.fields["state"] == ("sick", _tick(5))
    assert edited.fields["keep"] == (["alarm"], _tick(8))
    assert edited.fields["actor"] == ("phone", _tick(8))
    assert record.fields["keep"] == (["book"], _tick(5))


def test_record_hlc_is_the_greatest_field_clock() -> None:
    assert record_hlc(None) is None
    assert record_hlc(Record(id="x", fields={})) is None
    assert record_hlc(_sick((["book"], _tick(9, "phone")))) == _tick(9, "phone")
