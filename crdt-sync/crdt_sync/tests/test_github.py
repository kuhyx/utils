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
