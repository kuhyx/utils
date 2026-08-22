"""Tests for ``main()`` in ``tool/migrate_github_to_firebase``.

Split from :mod:`test_tool_migrate_github` to stay under the 250-line cap.

This is a one-shot destructive-ish migration, so the properties under test are
the safety ones: ``--dry-run`` must write nothing at all, the byte-for-byte
read-back must actually fail the run when a file does not round-trip, and the
report must be emitted *before* anything is written. ``main()`` reads argv
directly, so every test patches ``sys.argv``.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from tool import migrate_github_to_firebase as mg

_BLOBS = [
    mg.Blob(path="todo-sync/notes/a.json", text='{"a": 1}'),
    mg.Blob(path="diet-guard-sync/devices/pc/log.json", text='{"b": 2}'),
]


@pytest.fixture
def github() -> MagicMock:
    """Patch the whole GitHub-reading half with two migratable blobs."""
    entries = [(blob.path, f"sha-{index}") for index, blob in enumerate(_BLOBS)]
    entries.append(("todo-sync/changesets/old.json", "sha-skip"))

    with (
        patch.object(mg, "_github_session") as session,
        patch.object(mg, "_list_blobs", return_value=entries),
        patch.object(
            mg, "_fetch_blob", side_effect=lambda _s, path, _sha: _by_path(path)
        ),
        patch.object(mg, "_GITHUB_TOKEN_FILE", _token_file()),
    ):
        yield session


def _token_file() -> MagicMock:
    """A stand-in for the token path whose read_text yields a padded token."""
    token_file = MagicMock()
    token_file.read_text.return_value = "the-token\n"
    return token_file


def _by_path(path: str) -> mg.Blob:
    """Return the canned blob for ``path``."""
    return next(blob for blob in _BLOBS if blob.path == path)


def _client_that_round_trips() -> MagicMock:
    """A Firebase client whose read-back matches what was written."""
    written: dict[str, str] = {}
    client = MagicMock()
    client.put_file_text.side_effect = lambda path, text, **_: written.__setitem__(
        path, text
    )
    client.get_file_text.side_effect = written.get
    return client


def test_dry_run_writes_nothing(github: MagicMock) -> None:
    """The whole point of the flag: no client is even constructed."""
    with (
        patch.object(mg.sys, "argv", ["migrate", "--dry-run"]),
        patch.object(mg, "_firebase_client") as client_for,
    ):
        code = mg.main()

    assert code == 0
    client_for.assert_not_called()


def test_dry_run_still_reports_what_would_move(
    github: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A dry run that printed nothing would be useless."""
    with (
        patch.object(mg.sys, "argv", ["migrate", "--dry-run"]),
        patch.object(mg, "_firebase_client"),
        caplog.at_level(logging.INFO, logger="migrate"),
    ):
        mg.main()

    assert "2 files to migrate" in caplog.text
    assert "DRY RUN" in caplog.text


def test_the_skipped_paths_are_listed_with_their_reason(
    github: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Silently dropping files is the failure mode this reporting prevents."""
    with (
        patch.object(mg.sys, "argv", ["migrate", "--dry-run"]),
        patch.object(mg, "_firebase_client"),
        caplog.at_level(logging.INFO, logger="migrate"),
    ):
        mg.main()

    assert "1 skipped" in caplog.text
    assert "todo-sync/changesets/old.json" in caplog.text


def test_skipped_files_are_never_fetched(github: MagicMock) -> None:
    """Fetching then discarding would pay the egress the skip list avoids."""
    with (
        patch.object(mg.sys, "argv", ["migrate", "--dry-run"]),
        patch.object(mg, "_firebase_client"),
        patch.object(
            mg, "_fetch_blob", side_effect=lambda _s, p, _sha: _by_path(p)
        ) as f,
    ):
        mg.main()

    fetched = {c.args[1] for c in f.call_args_list}
    assert fetched == {blob.path for blob in _BLOBS}


def test_a_real_run_writes_every_blob_and_verifies(github: MagicMock) -> None:
    """The happy path: written, read back, byte-for-byte equal."""
    client = _client_that_round_trips()

    with (
        patch.object(mg.sys, "argv", ["migrate"]),
        patch.object(mg, "_firebase_client", return_value=client),
    ):
        code = mg.main()

    assert code == 0
    assert client.put_file_text.call_count == 2
    assert client.get_file_text.call_count == 2


def test_the_report_is_emitted_before_anything_is_written(
    github: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ordering matters: the operator sees the plan before it executes."""
    order: list[str] = []
    client = _client_that_round_trips()
    client.put_file_text.side_effect = lambda *a, **k: order.append("write")

    with (
        patch.object(mg.sys, "argv", ["migrate"]),
        patch.object(mg, "_firebase_client", return_value=client),
        patch.object(mg, "_report", side_effect=lambda *_: order.append("report")),
    ):
        mg.main()

    assert order[0] == "report"
    assert "write" in order


def test_a_file_that_does_not_round_trip_fails_the_run(github: MagicMock) -> None:
    """The check that makes 'OK' mean something.

    Without it a migration that silently dropped a file would report success,
    which is the one outcome worse than failing loudly.
    """
    client = MagicMock()
    client.get_file_text.return_value = "something else entirely"

    with (
        patch.object(mg.sys, "argv", ["migrate"]),
        patch.object(mg, "_firebase_client", return_value=client),
    ):
        code = mg.main()

    assert code == 1


def test_every_mismatching_path_is_named(
    github: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Reporting only the first would need N runs to find N problems."""
    client = MagicMock()
    client.get_file_text.return_value = None

    with (
        patch.object(mg.sys, "argv", ["migrate"]),
        patch.object(mg, "_firebase_client", return_value=client),
        caplog.at_level(logging.ERROR, logger="migrate"),
    ):
        mg.main()

    assert "2 file(s) did not round-trip" in caplog.text
    for blob in _BLOBS:
        assert blob.path in caplog.text


def test_a_partial_mismatch_still_fails(github: MagicMock) -> None:
    """One bad file out of two is a failed migration, not a 50% success."""
    client = MagicMock()
    client.get_file_text.side_effect = [_BLOBS[0].text, "corrupted"]

    with (
        patch.object(mg.sys, "argv", ["migrate"]),
        patch.object(mg, "_firebase_client", return_value=client),
    ):
        assert mg.main() == 1


def test_the_github_token_is_read_and_stripped(github: MagicMock) -> None:
    """A trailing newline in the token file would break the auth header."""
    client = _client_that_round_trips()

    with (
        patch.object(mg.sys, "argv", ["migrate"]),
        patch.object(mg, "_firebase_client", return_value=client),
    ):
        mg.main()

    github.assert_called_once_with("the-token")


def test_report_lists_the_largest_file_first(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Size order is what makes the report scannable for the costly ones."""
    blobs = [
        mg.Blob(path="small.json", text="x"),
        mg.Blob(path="large.json", text="x" * 100),
    ]

    with caplog.at_level(logging.INFO, logger="migrate"):
        mg._report(blobs, [])

    listed = [r.getMessage() for r in caplog.records if ".json" in r.getMessage()]
    assert "large.json" in listed[0]
    assert "small.json" in listed[1]


def test_report_omits_the_skipped_section_when_nothing_was_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An empty 'skipped' heading is noise that hides the real one."""
    with caplog.at_level(logging.INFO, logger="migrate"):
        mg._report([mg.Blob(path="a.json", text="x")], [])

    assert "skipped" not in caplog.text
