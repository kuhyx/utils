"""Tests for the GitHub-reading half of ``tool/migrate_github_to_firebase``.

``main()`` is covered in :mod:`test_tool_migrate_github_main`, split to stay
under the 250-line file cap.

Nothing here touches the network or the user's real config. The properties
worth pinning are the ones chosen deliberately over an easier alternative --
reading by sha rather than by path, refusing a truncated tree, and the skip
list -- because each was a decision with a stated cost, and a silent
regression in any of them produces a migration that *reports success* while
having moved the wrong bytes.
"""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
import requests

from tool import migrate_github_to_firebase as mg

if TYPE_CHECKING:
    from pathlib import Path


def _response(payload: object, *, status: int = 200) -> MagicMock:
    """Fake a ``requests`` response carrying ``payload`` as JSON."""
    response = MagicMock()
    response.status_code = status
    response.json.return_value = payload
    return response


def test_blob_size_is_measured_in_bytes_not_characters() -> None:
    """A multi-byte character would under-report the payload otherwise."""
    blob = mg.Blob(path="notes/a.json", text="café")

    assert len(blob.text) == 4
    assert blob.size == 5


def test_the_session_authenticates_and_asks_for_the_v3_api() -> None:
    """Without the Accept header GitHub may answer with a different shape."""
    session = mg._github_session("the-token")

    assert session.headers["Authorization"] == "Bearer the-token"
    assert session.headers["Accept"] == "application/vnd.github+json"


def test_the_session_retries_transient_failures() -> None:
    """A migration that gave up half-way is worse than one that never ran.

    403 and 429 are in the list because GitHub uses them for secondary rate
    limiting, which is the failure a bulk read actually hits.
    """
    session = mg._github_session("the-token")
    retry = session.get_adapter("https://api.github.com").max_retries

    assert retry.total == 5
    assert {403, 429, 500, 502, 503, 504} <= set(retry.status_forcelist)
    assert retry.raise_on_status is False


def test_listing_blobs_asks_for_one_recursive_tree() -> None:
    """One call rather than a walk; the walk would be N calls and race."""
    session = MagicMock()
    session.get.return_value = _response(
        {
            "truncated": False,
            "tree": [{"path": "a.json", "sha": "sha-a", "type": "blob"}],
        }
    )

    entries = mg._list_blobs(session)

    assert entries == [("a.json", "sha-a")]
    assert session.get.call_args.kwargs["params"] == {"recursive": "1"}


def test_directories_are_not_listed_as_blobs() -> None:
    """Tree entries include subtrees, which have no content to migrate."""
    session = MagicMock()
    session.get.return_value = _response(
        {
            "truncated": False,
            "tree": [
                {"path": "notes", "sha": "sha-dir", "type": "tree"},
                {"path": "notes/a.json", "sha": "sha-a", "type": "blob"},
            ],
        }
    )

    assert mg._list_blobs(session) == [("notes/a.json", "sha-a")]


def test_a_truncated_tree_is_refused_rather_than_partially_migrated() -> None:
    """The dangerous case: it would look like a successful smaller repo."""
    session = MagicMock()
    session.get.return_value = _response({"truncated": True, "tree": []})

    with pytest.raises(RuntimeError, match="truncated"):
        mg._list_blobs(session)


def test_an_http_error_listing_the_tree_is_raised() -> None:
    """A 404 must not read as an empty repo."""
    session = MagicMock()
    response = _response({}, status=404)
    response.raise_for_status.side_effect = requests.HTTPError("404")
    session.get.return_value = response

    with pytest.raises(requests.HTTPError):
        mg._list_blobs(session)


def test_a_blob_is_fetched_by_sha_rather_than_by_path() -> None:
    """Addressed by sha so a concurrent push cannot swap the content.

    The contents API would return whatever is at that path *now*, which need
    not be what the tree listing described.
    """
    session = MagicMock()
    content = base64.b64encode(b'{"v": 1}').decode()
    session.get.return_value = _response({"content": content})

    blob = mg._fetch_blob(session, "notes/a.json", "sha-a")

    assert blob == mg.Blob(path="notes/a.json", text='{"v": 1}')
    assert "git/blobs/sha-a" in session.get.call_args.args[0]


def test_a_blob_with_multibyte_content_round_trips() -> None:
    """The payload is decoded as UTF-8, not as latin-1 or bytes."""
    session = MagicMock()
    session.get.return_value = _response(
        {"content": base64.b64encode("café".encode()).decode()}
    )

    assert mg._fetch_blob(session, "a.txt", "sha").text == "café"


def test_an_http_error_fetching_a_blob_is_raised() -> None:
    """A dropped blob must fail the migration, not silently vanish."""
    session = MagicMock()
    response = _response({}, status=500)
    response.raise_for_status.side_effect = requests.HTTPError("500")
    session.get.return_value = response

    with pytest.raises(requests.HTTPError):
        mg._fetch_blob(session, "a.json", "sha")


@pytest.mark.parametrize(
    "path",
    [
        "todo-sync/changesets/0001.json",
        "diet-guard-sync/devices/desktop/log.json",
    ],
)
def test_the_deliberately_skipped_prefixes_are_skipped(path: str) -> None:
    """Each costs egress or storage forever and is verified redundant."""
    assert mg._should_migrate(path) is False


@pytest.mark.parametrize("path", ["README.md", "notes/README.md", ".gitkeep"])
def test_documentation_and_placeholders_are_skipped(path: str) -> None:
    """Not sync data; matched by name at any depth."""
    assert mg._should_migrate(path) is False


@pytest.mark.parametrize(
    "path",
    [
        "todo-sync/notes/a.json",
        "diet-guard-sync/devices/pc/log.json",
        "diet-guard-sync/devices/phone/log.json",
    ],
)
def test_real_sync_data_is_migrated(path: str) -> None:
    """The skip rules must not over-match the paths that carry the data."""
    assert mg._should_migrate(path) is True


def test_a_prefix_is_matched_at_the_start_only() -> None:
    """A skip prefix appearing mid-path is a different file."""
    assert mg._should_migrate("archive/todo-sync/changesets/x.json") is True


def test_the_firebase_client_signs_in_with_the_configured_account(
    tmp_path: Path,
) -> None:
    """Built from the shared config, not from per-tool credentials."""
    config = {
        "apiKey": "AIzaKey",
        "email": "sync@example.com",
        "databaseUrl": "https://project.firebasedatabase.app",
    }
    (tmp_path / "firebase.json").write_text(json.dumps(config), encoding="utf-8")
    (tmp_path / "password").write_text("the-account-phrase", encoding="utf-8")
    auth = MagicMock()

    with (
        patch.object(mg, "_CONFIG_DIR", tmp_path),
        patch.object(mg, "FirebaseTokenProvider", return_value=auth) as provider,
        patch.object(mg, "FirebaseSyncClient") as client,
    ):
        result = mg._firebase_client()

    assert provider.call_args.args[0] == "AIzaKey"
    auth.sign_in.assert_called_once_with("sync@example.com", "the-account-phrase")
    assert client.call_args.args == ("https://project.firebasedatabase.app", auth)
    assert result is client.return_value
