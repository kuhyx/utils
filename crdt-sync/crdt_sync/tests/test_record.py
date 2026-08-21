"""Tests for Record, merge_field, and merge_record."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from crdt_sync import Hlc, Record, merge_field, merge_record

if TYPE_CHECKING:
    from collections.abc import Callable


class TestMergeField:
    """Merge field."""

    def test_greater_hlc_wins(self, make_hlc: Callable[..., Hlc]) -> None:
        """Greater HLC wins."""
        older = ("a", make_hlc(100))
        newer = ("b", make_hlc(200))
        assert merge_field(older, newer) == newer
        assert merge_field(newer, older) == newer

    def test_equal_hlc_keeps_the_first_argument(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        """Equal HLC keeps the first argument."""
        clock = make_hlc(100)
        a = ("a", clock)
        b = ("a", clock)
        assert merge_field(a, b) == a


class TestMergeRecord:
    """Merge record."""

    def test_raises_when_ids_differ(self) -> None:
        """Raises when ids differ."""
        a = Record(id="a", fields={})
        b = Record(id="b", fields={})
        with pytest.raises(ValueError, match="different ids"):
            merge_record(a, b)

    def test_merges_disjoint_fields(self, make_hlc: Callable[..., Hlc]) -> None:
        """Merges disjoint fields."""
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
        """Shared field keeps the later write."""
        a = Record(id="x", fields={"text": ("old", make_hlc(100))})
        b = Record(id="x", fields={"text": ("new", make_hlc(200))})
        merged = merge_record(a, b)
        assert merged.fields["text"] == ("new", make_hlc(200))

    def test_delete_is_sticky_against_an_older_non_deleted_copy(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        """Delete is sticky against an older non deleted copy."""
        deleted = Record(id="x", fields={}, deleted=True, deleted_hlc=make_hlc(200))
        stale = Record(id="x", fields={"text": ("resurrected", make_hlc(100))})
        assert merge_record(deleted, stale).deleted is True
        assert merge_record(stale, deleted).deleted is True

    def test_neither_side_deleted_stays_not_deleted(self) -> None:
        """Neither side deleted stays not deleted."""
        a = Record(id="x", fields={})
        b = Record(id="x", fields={})
        merged = merge_record(a, b)
        assert merged.deleted is False
        assert merged.deleted_hlc is None

    def test_both_sides_deleted_keeps_the_later_delete_clock(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        """Both sides deleted keeps the later delete clock."""
        a = Record(id="x", fields={}, deleted=True, deleted_hlc=make_hlc(100))
        b = Record(id="x", fields={}, deleted=True, deleted_hlc=make_hlc(200))
        merged = merge_record(a, b)
        assert merged.deleted_hlc == make_hlc(200)

    def test_both_deleted_but_one_side_missing_a_clock_keeps_the_other(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        """Both deleted but one side missing a clock keeps the other."""
        a = Record(id="x", fields={}, deleted=True, deleted_hlc=None)
        b = Record(id="x", fields={}, deleted=True, deleted_hlc=make_hlc(200))
        assert merge_record(a, b).deleted_hlc == make_hlc(200)
        assert merge_record(b, a).deleted_hlc == make_hlc(200)

    def test_is_commutative(self, make_hlc: Callable[..., Hlc]) -> None:
        """Is commutative."""
        record_a = Record(id="x", fields={"text": ("a", make_hlc(100))})
        record_b = Record(
            id="x", fields={"text": ("b", make_hlc(200)), "extra": ("e", make_hlc(1))}
        )
        assert merge_record(record_a, record_b) == merge_record(record_b, record_a)

    def test_is_idempotent(self, make_hlc: Callable[..., Hlc]) -> None:
        """Is idempotent."""
        record = Record(id="x", fields={"text": ("a", make_hlc(100))})
        assert merge_record(record, record) == record


class TestRecordDictRoundTrip:
    """Record dict round trip."""

    def test_round_trips_a_record_with_fields(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        """Round trips a record with fields."""
        record = Record(id="x", fields={"text": ("hello", make_hlc(100, node_id="pc"))})
        assert Record.from_dict(record.to_dict()) == record

    def test_round_trips_a_deleted_record(self, make_hlc: Callable[..., Hlc]) -> None:
        """Round trips a deleted record."""
        record = Record(id="x", fields={}, deleted=True, deleted_hlc=make_hlc(200))
        assert Record.from_dict(record.to_dict()) == record

    def test_round_trips_a_record_with_no_delete_clock(self) -> None:
        """Round trips a record with no delete clock."""
        record = Record(id="x", fields={}, deleted=False, deleted_hlc=None)
        assert Record.from_dict(record.to_dict()) == record


class TestCrossLanguageWireFormat:
    """Pins the exact wire shape shared with crdt_sync_dart's Record.

    Values chosen here are duplicated verbatim in crdt_sync_dart's
    `test/record_test.dart` (see its ``TestCrossLanguageWireFormat``
    group). If this test and that one both pass, the two languages agree
    on the wire format; if only one changes, the two suites diverge and
    at least one of them fails -- catching exactly the kind of
    key-naming mismatch (``deleted_hlc`` vs ``deletedHlc``) that neither
    language's own round-trip test can see on its own.
    """

    def test_matches_the_fixture_shared_with_the_dart_package(self) -> None:
        """Matches the fixture shared with the dart package."""
        record = Record(
            id="abc123",
            fields={"text": ("hello", Hlc(wall_time_ms=100, counter=0, node_id="pc"))},
            deleted=True,
            deleted_hlc=Hlc(wall_time_ms=1000, counter=0, node_id="node-a"),
        )
        expected = {
            "id": "abc123",
            "fields": {"text": ["hello", "1970-01-01T00:00:00.100Z-0000-pc"]},
            "deleted": True,
            "deleted_hlc": "1970-01-01T00:00:01.000Z-0000-node-a",
        }
        assert record.to_dict() == expected
        assert Record.from_dict(expected) == record
