"""Tests for ``tool/interop_seed``, the Python half of the interop check.

Patched at the module's own boundary -- ``firebase_client_for``,
``FirebaseConfig.load`` and ``sync_log`` -- so nothing touches Firebase. What
is worth asserting here is not that ``sync_log`` works (``test_sync.py`` covers
that) but that this tool hands it *exactly* the shape the Dart side looks for:
the seed exists to make ``crdt_sync_dart/tool/interop_check.dart`` pass, and a
drifted path prefix, device id or record id would make the two halves silently
miss each other, which is the failure the pair exists to catch.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from crdt_sync import Hlc, Record
from tool import interop_seed

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def seeded() -> Iterator[tuple[int, MagicMock, MagicMock, MagicMock]]:
    """Run ``main()`` with the network boundary mocked out.

    Yields the exit code plus the three mocks whose call arguments are what
    the assertions below are actually about.
    """
    with (
        patch.object(interop_seed, "firebase_client_for") as client_for,
        patch.object(interop_seed.FirebaseConfig, "load") as load,
        patch.object(interop_seed, "sync_log", return_value={"py-rec": None}) as synced,
    ):
        code = interop_seed.main()
        yield code, synced, client_for, load


def test_main_reports_success(seeded: tuple) -> None:
    """A successful seed is exit code 0."""
    code, _, _, _ = seeded

    assert code == 0


def test_the_client_is_built_for_the_interop_app_from_the_shared_config(
    seeded: tuple,
) -> None:
    """The app name selects the credential cache; interop has its own."""
    _, _, client_for, load = seeded

    load.assert_called_once_with()
    assert client_for.call_args.args == ("interop",)
    assert client_for.call_args.kwargs["config"] is load.return_value


def test_the_target_matches_what_the_dart_checker_reads(seeded: tuple) -> None:
    """The path prefix and device id the Dart half looks under.

    ``interop_check.dart`` reads ``_interop/devices``; a drift on either side
    makes the check fail as "Python wrote nothing" rather than as a mismatch.
    """
    _, synced, client_for, _ = seeded
    target = synced.call_args.args[0]

    assert target.path_prefix == "_interop/devices"
    assert target.device_id == "pydev"
    assert target.client is client_for.return_value


def test_the_seeded_record_is_the_one_the_dart_side_asserts_on(
    seeded: tuple,
) -> None:
    """py-rec, with the value and Hlc the Dart checker compares against."""
    _, synced, _, _ = seeded
    records = synced.call_args.args[1]

    assert set(records) == {"py-rec"}
    record = records["py-rec"]
    assert isinstance(record, Record)
    assert record.id == "py-rec"
    value, hlc = record.fields["value"]
    assert value == "written-by-python"
    assert hlc == Hlc(wall_time_ms=1000, counter=0, node_id="node-py")


def test_the_librarys_own_codec_is_used_rather_than_a_local_one(
    seeded: tuple,
) -> None:
    """Reimplementing the encoding here would test the wrong thing.

    The check is that what the real apps write is what the other language
    reads, so the codec must be the library's canonical pair.
    """
    _, synced, _, _ = seeded
    codec = synced.call_args.args[2]

    assert codec.decode is interop_seed.load_log
    assert codec.encode is interop_seed.dump_log


def test_revision_state_is_in_memory_so_reruns_reseed(seeded: tuple) -> None:
    """A persisted cursor would make a second run write nothing.

    The Dart half deletes both devices' data on its way out, so the seed has
    to be repeatable; remembering a revision across runs would break that.
    """
    _, synced, _, _ = seeded
    tracking = synced.call_args.args[3]

    assert isinstance(tracking.state_store, interop_seed.MemorySyncStateStore)


def test_main_reports_what_python_can_see_and_the_next_command(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The output is the operator's only signal that the seed landed."""
    with (
        patch.object(interop_seed, "firebase_client_for"),
        patch.object(interop_seed.FirebaseConfig, "load"),
        patch.object(
            interop_seed, "sync_log", return_value={"py-rec": None, "a": None}
        ),
        caplog.at_level(logging.INFO, logger="interop-seed"),
    ):
        interop_seed.main()

    messages = [record.getMessage() for record in caplog.records]
    assert any("['a', 'py-rec']" in message for message in messages)
    assert any("dart run tool/interop_check.dart" in message for message in messages)
