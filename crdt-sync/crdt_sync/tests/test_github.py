"""Tests for the GitHub Contents API sync client.

The HTTP layer is fully mocked (``requests.get``/``requests.put``), so every
branch -- success, path-404-but-repo-ok, repo-404, non-2xx, and network
exceptions -- is exercised without any network access.
"""

from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import pytest
import requests

from crdt_sync import (
    GitHubSyncClient,
    GitHubSyncError,
    RemoteNotFoundError,
    RemoteStore,
    RemoteSyncError,
    RepoNotFoundError,
    _github,
)


def _response(status_code: int = 200, json_data: object = None) -> MagicMock:
    """Build a fake ``requests.Response`` with a fixed status and JSON body."""
    response = MagicMock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 300
    response.json = MagicMock(return_value=json_data if json_data is not None else {})
    return response


def _client() -> GitHubSyncClient:
    return GitHubSyncClient("kuhyx", "crdt-sync-demo", "fake-token")


def _patch_get(*responses: MagicMock) -> object:
    """Patch ``requests.get`` to return each of ``responses`` in order."""
    return patch.object(_github.requests, "get", side_effect=list(responses))


def _patch_get_raises() -> object:
    return patch.object(
        _github.requests,
        "get",
        side_effect=requests.ConnectionError("offline"),
    )


class TestGetFileText:
    """Get file text."""

    def test_returns_decoded_content_on_success(self) -> None:
        """Returns decoded content on success."""
        encoded = base64.b64encode(b"hello world").decode("ascii")
        with _patch_get(_response(200, {"content": encoded})):
            assert _client().get_file_text("devices/pc/log.json") == "hello world"

    def test_returns_none_for_an_unused_path_on_a_real_repo(self) -> None:
        """Returns none for an unused path on a real repo."""
        with _patch_get(_response(404), _response(200)):
            assert _client().get_file_text("devices/phone/log.json") is None

    def test_raises_repo_not_found_when_the_repo_itself_is_missing(self) -> None:
        """Raises repo not found when the repo itself is missing."""
        with (
            _patch_get(_response(404), _response(404)),
            pytest.raises(RepoNotFoundError),
        ):
            _client().get_file_text("devices/pc/log.json")

    def test_raises_sync_error_on_a_non_2xx_non_404(self) -> None:
        """Raises sync error on a non 2xx non 404."""
        with _patch_get(_response(500)), pytest.raises(GitHubSyncError):
            _client().get_file_text("devices/pc/log.json")

    def test_raises_sync_error_on_a_network_exception(self) -> None:
        """Raises sync error on a network exception."""
        with _patch_get_raises(), pytest.raises(GitHubSyncError):
            _client().get_file_text("devices/pc/log.json")

    def test_treats_a_network_error_during_the_repo_check_as_repo_missing(
        self,
    ) -> None:
        """Treats a network error during the repo check as repo missing."""
        with (
            patch.object(
                _github.requests,
                "get",
                side_effect=[_response(404), requests.ConnectionError("offline")],
            ),
            pytest.raises(RepoNotFoundError),
        ):
            _client().get_file_text("devices/pc/log.json")


class TestListDirectory:
    """List directory."""

    def test_returns_entry_names(self) -> None:
        """Returns entry names."""
        payload = [{"name": "pc"}, {"name": "phone"}, {"not_a_name": "x"}]
        with _patch_get(_response(200, payload)):
            assert _client().list_directory("devices") == ["pc", "phone"]

    def test_returns_empty_list_when_response_is_not_a_list(self) -> None:
        """Returns empty list when response is not a list."""
        with _patch_get(_response(200, {"unexpected": "shape"})):
            assert _client().list_directory("devices") == []

    def test_returns_empty_list_for_an_unused_path_on_a_real_repo(self) -> None:
        """Returns empty list for an unused path on a real repo."""
        with _patch_get(_response(404), _response(200)):
            assert _client().list_directory("devices") == []

    def test_raises_repo_not_found_when_the_repo_itself_is_missing(self) -> None:
        """Raises repo not found when the repo itself is missing."""
        with (
            _patch_get(_response(404), _response(404)),
            pytest.raises(RepoNotFoundError),
        ):
            _client().list_directory("devices")

    def test_raises_sync_error_on_a_non_2xx_non_404(self) -> None:
        """Raises sync error on a non 2xx non 404."""
        with _patch_get(_response(500)), pytest.raises(GitHubSyncError):
            _client().list_directory("devices")


class TestPutFileText:
    """Put file text."""

    def test_creates_a_new_file_with_no_sha_when_none_existed(self) -> None:
        """Creates a new file with no sha when none existed."""
        with (
            _patch_get(_response(404), _response(200)),
            patch.object(
                _github.requests, "put", return_value=_response(201)
            ) as put_mock,
        ):
            _client().put_file_text("devices/pc/log.json", "{}", message="m")
        assert "sha" not in put_mock.call_args.kwargs["json"]

    def test_updates_an_existing_file_by_including_its_sha(self) -> None:
        """Updates an existing file by including its sha."""
        with (
            _patch_get(_response(200, {"sha": "abc123"})),
            patch.object(
                _github.requests, "put", return_value=_response(200)
            ) as put_mock,
        ):
            _client().put_file_text("devices/pc/log.json", "{}", message="m")
        assert put_mock.call_args.kwargs["json"]["sha"] == "abc123"

    def test_treats_a_non_string_sha_field_as_absent(self) -> None:
        """Treats a non string sha field as absent."""
        with (
            _patch_get(_response(200, {"sha": 12345})),
            patch.object(
                _github.requests, "put", return_value=_response(200)
            ) as put_mock,
        ):
            _client().put_file_text("devices/pc/log.json", "{}", message="m")
        assert "sha" not in put_mock.call_args.kwargs["json"]

    def test_raises_repo_not_found_when_checking_sha_on_a_missing_repo(self) -> None:
        """Raises repo not found when checking sha on a missing repo."""
        with (
            _patch_get(_response(404), _response(404)),
            pytest.raises(RepoNotFoundError),
        ):
            _client().put_file_text("devices/pc/log.json", "{}", message="m")

    def test_raises_sync_error_when_the_sha_check_itself_fails(self) -> None:
        """Raises sync error when the sha check itself fails."""
        with _patch_get(_response(500)), pytest.raises(GitHubSyncError):
            _client().put_file_text("devices/pc/log.json", "{}", message="m")

    def test_raises_sync_error_on_a_put_network_exception(self) -> None:
        """Raises sync error on a put network exception."""
        with (
            _patch_get(_response(404), _response(200)),
            patch.object(
                _github.requests,
                "put",
                side_effect=requests.ConnectionError("offline"),
            ),
            pytest.raises(GitHubSyncError),
        ):
            _client().put_file_text("devices/pc/log.json", "{}", message="m")

    def test_raises_sync_error_on_a_put_non_2xx_response(self) -> None:
        """Raises sync error on a put non 2xx response."""
        with (
            _patch_get(_response(404), _response(200)),
            patch.object(_github.requests, "put", return_value=_response(422)),
            pytest.raises(GitHubSyncError),
        ):
            _client().put_file_text("devices/pc/log.json", "{}", message="m")


class TestCanAccessRepo:
    """Can access repo."""

    def test_true_when_repo_endpoint_ok(self) -> None:
        """True when repo endpoint ok."""
        with _patch_get(_response(200)):
            assert _client().can_access_repo() is True

    def test_false_when_repo_is_missing(self) -> None:
        """False when repo is missing."""
        with _patch_get(_response(404)):
            assert _client().can_access_repo() is False

    def test_false_on_a_network_error(self) -> None:
        """False on a network error."""
        with _patch_get_raises():
            assert _client().can_access_repo() is False


class TestCanAccessRemote:
    """The ``RemoteStore`` spelling must behave exactly like the legacy name."""

    def test_true_when_repo_endpoint_ok(self) -> None:
        """True when repo endpoint ok."""
        with _patch_get(_response(200)):
            assert _client().can_access_remote() is True

    def test_false_when_repo_is_missing(self) -> None:
        """False when repo is missing."""
        with _patch_get(_response(404)):
            assert _client().can_access_remote() is False

    def test_false_on_a_network_error(self) -> None:
        """False on a network error."""
        with _patch_get_raises():
            assert _client().can_access_remote() is False


class TestRemoteStoreContract:
    """The seam sync talks through must actually be satisfied by the client."""

    def test_github_client_is_a_remote_store(self) -> None:
        """Github client is a remote store."""
        assert isinstance(_client(), RemoteStore)

    def test_repo_not_found_is_catchable_as_either_error(self) -> None:
        # Backend-neutral callers catch RemoteNotFoundError; existing GitHub
        # callers catch GitHubSyncError. One exception must satisfy both.
        """Repo not found is catchable as either error."""
        error = RepoNotFoundError("gone")
        assert isinstance(error, GitHubSyncError)
        assert isinstance(error, RemoteNotFoundError)
        assert isinstance(error, RemoteSyncError)


class TestDeleteFile:
    """Delete file."""

    def test_deletes_an_existing_file_resolving_its_own_sha(self) -> None:
        """Deletes an existing file resolving its own sha."""
        with (
            _patch_get(_response(200, {"sha": "abc123"})),
            patch.object(_github.requests, "delete", return_value=_response(200)),
        ):
            _client().delete_file("devices/pc/log.json")

    def test_is_a_no_op_when_the_file_is_absent(self) -> None:
        # sha GET 404, repo-exists GET 200 -> None sha -> no DELETE sent.
        """Is a no op when the file is absent."""
        with (
            _patch_get(_response(404), _response(200)),
            patch.object(_github.requests, "delete") as mock_delete,
        ):
            _client().delete_file("devices/pc/gone.json")
            mock_delete.assert_not_called()

    def test_raises_on_a_delete_non_2xx_response(self) -> None:
        """Raises on a delete non 2xx response."""
        with (
            _patch_get(_response(200, {"sha": "abc123"})),
            patch.object(_github.requests, "delete", return_value=_response(500)),
            pytest.raises(GitHubSyncError),
        ):
            _client().delete_file("devices/pc/log.json")

    def test_raises_on_a_delete_network_error(self) -> None:
        """Raises on a delete network error."""
        with (
            _patch_get(_response(200, {"sha": "abc123"})),
            patch.object(
                _github.requests,
                "delete",
                side_effect=requests.ConnectionError("offline"),
            ),
            pytest.raises(GitHubSyncError),
        ):
            _client().delete_file("devices/pc/log.json")
