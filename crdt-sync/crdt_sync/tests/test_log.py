"""Tests for merge_logs, including its CRDT convergence properties."""

from __future__ import annotations

from typing import TYPE_CHECKING

from crdt_sync import Hlc, Record, merge_logs

if TYPE_CHECKING:
    from collections.abc import Callable

    from crdt_sync import Log


class TestMergeLogs:
    def test_returns_the_union_of_disjoint_ids(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        local = {"a": Record(id="a", fields={"text": ("a", make_hlc(100))})}
        remote = {"b": Record(id="b", fields={"text": ("b", make_hlc(100))})}
        assert merge_logs(local, remote) == {**local, **remote}

    def test_merges_a_shared_id_field_by_field(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        local = {"a": Record(id="a", fields={"text": ("old", make_hlc(100))})}
        remote = {"a": Record(id="a", fields={"text": ("new", make_hlc(200))})}
        merged = merge_logs(local, remote)
        assert merged["a"].fields["text"] == ("new", make_hlc(200))

    def test_a_delete_on_one_side_survives_the_merge(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        local = {
            "a": Record(id="a", fields={}, deleted=True, deleted_hlc=make_hlc(200))
        }
        remote = {"a": Record(id="a", fields={"text": ("still here", make_hlc(100))})}
        assert merge_logs(local, remote)["a"].deleted is True

    def test_does_not_mutate_either_input(self, make_hlc: Callable[..., Hlc]) -> None:
        local = {"a": Record(id="a", fields={"text": ("a", make_hlc(100))})}
        remote = {"b": Record(id="b", fields={"text": ("b", make_hlc(100))})}
        local_before = dict(local)
        remote_before = dict(remote)
        merge_logs(local, remote)
        assert local == local_before
        assert remote == remote_before


class TestConvergenceProperties:
    def _sample_logs(self, make_hlc: Callable[..., Hlc]) -> tuple[Log, Log]:
        a = {
            "shared": Record(
                id="shared", fields={"text": ("a-version", make_hlc(100))}
            ),
            "only-in-a": Record(id="only-in-a", fields={"text": ("a", make_hlc(50))}),
        }
        b = {
            "shared": Record(
                id="shared", fields={"text": ("b-version", make_hlc(200))}
            ),
            "only-in-b": Record(id="only-in-b", fields={"text": ("b", make_hlc(50))}),
        }
        return a, b

    def test_is_commutative(self, make_hlc: Callable[..., Hlc]) -> None:
        a, b = self._sample_logs(make_hlc)
        assert merge_logs(a, b) == merge_logs(b, a)

    def test_is_idempotent(self, make_hlc: Callable[..., Hlc]) -> None:
        a, _ = self._sample_logs(make_hlc)
        assert merge_logs(a, a) == a

    def test_repeated_merge_of_the_same_remote_is_a_no_op(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        a, b = self._sample_logs(make_hlc)
        once = merge_logs(a, b)
        twice = merge_logs(once, b)
        assert once == twice
