"""Tests for Record, merge_field, and merge_record."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from crdt_sync import Hlc, Record, merge_field, merge_record

if TYPE_CHECKING:
    from collections.abc import Callable


class TestMergeField:
    def test_greater_hlc_wins(self, make_hlc: Callable[..., Hlc]) -> None:
        older = ("a", make_hlc(100))
        newer = ("b", make_hlc(200))
        assert merge_field(older, newer) == newer
        assert merge_field(newer, older) == newer

    def test_equal_hlc_keeps_the_first_argument(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        clock = make_hlc(100)
        a = ("a", clock)
        b = ("a", clock)
        assert merge_field(a, b) == a


class TestMergeRecord:
    def test_raises_when_ids_differ(self) -> None:
        a = Record(id="a", fields={})
        b = Record(id="b", fields={})
        with pytest.raises(ValueError, match="different ids"):
            merge_record(a, b)

    def test_merges_disjoint_fields(self, make_hlc: Callable[..., Hlc]) -> None:
        a = Record(id="x", fields={"text": ("hello", make_hlc(100))})
        b = Record(id="x", fields={"priority": ("high", make_hlc(50))})
        merged = merge_record(a, b)
        assert merged.fields == {
            "text": ("hello", make_hlc(100)),
            "priority": ("high", make_hlc(50)),
        }

    def test_shared_field_keeps_the_later_write(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        a = Record(id="x", fields={"text": ("old", make_hlc(100))})
        b = Record(id="x", fields={"text": ("new", make_hlc(200))})
        merged = merge_record(a, b)
        assert merged.fields["text"] == ("new", make_hlc(200))

    def test_delete_is_sticky_against_an_older_non_deleted_copy(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        deleted = Record(id="x", fields={}, deleted=True, deleted_hlc=make_hlc(200))
        stale = Record(id="x", fields={"text": ("resurrected", make_hlc(100))})
        assert merge_record(deleted, stale).deleted is True
        assert merge_record(stale, deleted).deleted is True

    def test_neither_side_deleted_stays_not_deleted(self) -> None:
        a = Record(id="x", fields={})
        b = Record(id="x", fields={})
        merged = merge_record(a, b)
        assert merged.deleted is False
        assert merged.deleted_hlc is None

    def test_both_sides_deleted_keeps_the_later_delete_clock(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        a = Record(id="x", fields={}, deleted=True, deleted_hlc=make_hlc(100))
        b = Record(id="x", fields={}, deleted=True, deleted_hlc=make_hlc(200))
        merged = merge_record(a, b)
        assert merged.deleted_hlc == make_hlc(200)

    def test_both_deleted_but_one_side_missing_a_clock_keeps_the_other(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        a = Record(id="x", fields={}, deleted=True, deleted_hlc=None)
        b = Record(id="x", fields={}, deleted=True, deleted_hlc=make_hlc(200))
        assert merge_record(a, b).deleted_hlc == make_hlc(200)
        assert merge_record(b, a).deleted_hlc == make_hlc(200)

    def test_is_commutative(self, make_hlc: Callable[..., Hlc]) -> None:
        record_a = Record(id="x", fields={"text": ("a", make_hlc(100))})
        record_b = Record(
            id="x", fields={"text": ("b", make_hlc(200)), "extra": ("e", make_hlc(1))}
        )
        assert merge_record(record_a, record_b) == merge_record(record_b, record_a)

    def test_is_idempotent(self, make_hlc: Callable[..., Hlc]) -> None:
        record = Record(id="x", fields={"text": ("a", make_hlc(100))})
        assert merge_record(record, record) == record


class TestRecordDictRoundTrip:
    def test_round_trips_a_record_with_fields(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        record = Record(id="x", fields={"text": ("hello", make_hlc(100, node_id="pc"))})
        assert Record.from_dict(record.to_dict()) == record

    def test_round_trips_a_deleted_record(self, make_hlc: Callable[..., Hlc]) -> None:
        record = Record(id="x", fields={}, deleted=True, deleted_hlc=make_hlc(200))
        assert Record.from_dict(record.to_dict()) == record

    def test_round_trips_a_record_with_no_delete_clock(self) -> None:
        record = Record(id="x", fields={}, deleted=False, deleted_hlc=None)
        assert Record.from_dict(record.to_dict()) == record
