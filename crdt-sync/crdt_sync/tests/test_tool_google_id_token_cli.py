"""Tests for ``tool/google_id_token``'s command line entry point.

Split from :mod:`test_tool_google_id_token` to stay under the repo's 250-line
file cap. That module covers the OAuth flow itself; this one covers ``main()``
-- argument parsing, where the token is written, and the exit code -- with
``fetch_id_token`` patched out, since the flow is already exercised there.

The shared fixture values are imported rather than redeclared so the two
files cannot drift.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from crdt_sync.tests.test_tool_google_id_token import (
    _CLIENT_CREDENTIAL,
    _CLIENT_ID,
    _ID_VALUE,
)
from tool import google_id_token as git

if TYPE_CHECKING:
    from pathlib import Path


def test_main_prints_the_token_when_no_output_is_given(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Default: the token goes to the log for copy-paste."""
    with (
        patch.object(git, "fetch_id_token", return_value=_ID_VALUE),
        caplog.at_level(logging.INFO, logger="google_id_token"),
    ):
        code = git.main(
            ["--client-id", _CLIENT_ID, "--client-secret", _CLIENT_CREDENTIAL]
        )

    assert code == 0
    assert any(record.getMessage() == _ID_VALUE for record in caplog.records)


def test_main_writes_the_token_to_a_file_at_mode_0600(tmp_path: Path) -> None:
    """An ID token is a bearer credential, so the file must not be readable."""
    destination = tmp_path / "token.txt"

    with patch.object(git, "fetch_id_token", return_value=_ID_VALUE):
        code = git.main(
            [
                "--client-id",
                _CLIENT_ID,
                "--client-secret",
                _CLIENT_CREDENTIAL,
                "--output",
                str(destination),
            ]
        )

    assert code == 0
    assert destination.read_text(encoding="utf-8") == _ID_VALUE
    assert destination.stat().st_mode & 0o777 == 0o600


def test_main_passes_no_browser_and_port_through() -> None:
    """The two flags that decide whether the flow can work at all."""
    with patch.object(git, "fetch_id_token", return_value=_ID_VALUE) as fetch:
        git.main(
            [
                "--client-id",
                _CLIENT_ID,
                "--client-secret",
                _CLIENT_CREDENTIAL,
                "--no-browser",
                "--port",
                "8765",
            ]
        )

    assert fetch.call_args.kwargs == {"open_browser": False, "port": 8765}


def test_main_returns_1_when_the_flow_fails() -> None:
    """A TokenError is an exit code, not a traceback."""
    with patch.object(git, "fetch_id_token", side_effect=git.TokenError("nope")):
        code = git.main(
            ["--client-id", _CLIENT_ID, "--client-secret", _CLIENT_CREDENTIAL]
        )

    assert code == 1
