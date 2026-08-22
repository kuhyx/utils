"""Tests for ``_read_token`` and ``main()`` in ``tool/link_google``.

Split from :mod:`test_tool_link_google` to stay under the 250-line cap.

``main()`` catches three exception types by name rather than with a bare
``except Exception``, deliberately, so that an unanticipated bug still
surfaces as a traceback instead of a tidy "FAIL" line. That distinction is
asserted here: the three named failures return 1, and anything else escapes.
"""

from __future__ import annotations

import argparse
import logging
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from crdt_sync._config import ConfigError
from crdt_sync._firebase_auth import FirebaseAuthError
from crdt_sync.tests.test_tool_link_google import _CONFIG, _UID, _google_token
from tool import link_google as lg

if TYPE_CHECKING:
    from pathlib import Path


def _args(
    token: str | None = None, token_file: str | None = None
) -> argparse.Namespace:
    """Build the namespace ``_read_token`` reads."""
    return argparse.Namespace(
        google_id_token=token,
        google_id_token_file=token_file,
    )


def test_a_token_is_read_from_the_command_line() -> None:
    """The inline form."""
    assert lg._read_token(_args("the-token")) == "the-token"


def test_a_token_is_read_from_a_file(tmp_path: Path) -> None:
    """The file form, which is what the paired minting tool writes."""
    path = tmp_path / "token.txt"
    path.write_text("the-token", encoding="utf-8")

    assert lg._read_token(_args(token_file=str(path))) == "the-token"


def test_a_trailing_newline_is_stripped(tmp_path: Path) -> None:
    """A token written by a file or heredoc picks one up.

    Firebase rejects it with an unhelpful message, so stripping here is what
    keeps that from becoming a debugging session.
    """
    path = tmp_path / "token.txt"
    path.write_text("the-token\n", encoding="utf-8")

    assert lg._read_token(_args(token_file=str(path))) == "the-token"


def test_an_unreadable_token_file_is_reported_by_path(tmp_path: Path) -> None:
    """Naming the path is the difference between a fix and a guess."""
    missing = tmp_path / "absent.txt"

    with pytest.raises(lg.LinkError, match="could not be read"):
        lg._read_token(_args(token_file=str(missing)))


def test_an_empty_token_is_rejected(tmp_path: Path) -> None:
    """An empty file would otherwise be sent to Firebase as a valid request."""
    path = tmp_path / "token.txt"
    path.write_text("   \n", encoding="utf-8")

    with pytest.raises(lg.LinkError, match="is empty"):
        lg._read_token(_args(token_file=str(path)))


def test_an_empty_inline_token_is_rejected() -> None:
    """Same check, the other input route."""
    with pytest.raises(lg.LinkError, match="is empty"):
        lg._read_token(_args(""))


def test_main_links_and_reports_the_unchanged_uid(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The happy path: exit 0, and the uid echoed so it can be eyeballed."""
    with (
        patch.object(lg.FirebaseConfig, "load", return_value=_CONFIG),
        patch.object(lg, "link_google", return_value=_UID) as linked,
        caplog.at_level(logging.INFO, logger="link_google"),
    ):
        code = lg.main(["--google-id-token", _google_token()])

    assert code == 0
    assert linked.call_count == 1
    assert "uid unchanged" in caplog.text
    assert _UID in caplog.text


def test_main_describes_the_token_before_linking(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The operator's chance to abort on the wrong Google account."""
    with (
        patch.object(lg.FirebaseConfig, "load", return_value=_CONFIG),
        patch.object(lg, "link_google", return_value=_UID),
        caplog.at_level(logging.INFO, logger="link_google"),
    ):
        lg.main(["--google-id-token", _google_token()])

    assert "person@gmail.com" in caplog.text
    assert "linking onto sync@example.com" in caplog.text


def test_main_points_at_the_verification_step(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Linking is only half the job; the preflight is what confirms it."""
    with (
        patch.object(lg.FirebaseConfig, "load", return_value=_CONFIG),
        patch.object(lg, "link_google", return_value=_UID),
        caplog.at_level(logging.INFO, logger="link_google"),
    ):
        lg.main(["--google-id-token", _google_token()])

    assert "tool/preflight_firebase.py" in caplog.text


def test_main_reads_the_token_from_a_file(tmp_path: Path) -> None:
    """The --google-id-token-file route reaches link_google intact."""
    path = tmp_path / "token.txt"
    token = _google_token()
    path.write_text(f"{token}\n", encoding="utf-8")

    with (
        patch.object(lg.FirebaseConfig, "load", return_value=_CONFIG),
        patch.object(lg, "link_google", return_value=_UID) as linked,
    ):
        code = lg.main(["--google-id-token-file", str(path)])

    assert code == 0
    assert linked.call_args.args[1] == token


def test_main_returns_1_on_a_link_error(caplog: pytest.LogCaptureFixture) -> None:
    """The uid mismatch and every other LinkError."""
    with (
        patch.object(lg.FirebaseConfig, "load", return_value=_CONFIG),
        patch.object(lg, "link_google", side_effect=lg.LinkError("wrong account")),
        caplog.at_level(logging.INFO, logger="link_google"),
    ):
        code = lg.main(["--google-id-token", _google_token()])

    assert code == 1
    assert "FAIL" in caplog.text


def test_main_returns_1_on_a_config_error(caplog: pytest.LogCaptureFixture) -> None:
    """An unusable firebase.json is a reported failure, not a traceback."""
    with (
        patch.object(lg.FirebaseConfig, "load", side_effect=ConfigError("no config")),
        caplog.at_level(logging.INFO, logger="link_google"),
    ):
        code = lg.main(["--google-id-token", _google_token()])

    assert code == 1
    assert "FAIL" in caplog.text


def test_main_returns_1_on_an_auth_error(caplog: pytest.LogCaptureFixture) -> None:
    """A rejected password, the third named failure."""
    with (
        patch.object(lg.FirebaseConfig, "load", return_value=_CONFIG),
        patch.object(lg, "link_google", side_effect=FirebaseAuthError("bad password")),
        caplog.at_level(logging.INFO, logger="link_google"),
    ):
        code = lg.main(["--google-id-token", _google_token()])

    assert code == 1
    assert "FAIL" in caplog.text


def test_main_rejects_a_malformed_token_before_touching_the_network() -> None:
    """The local shape check exists to save a round trip; prove it does."""
    with (
        patch.object(lg.FirebaseConfig, "load") as load,
        patch.object(lg, "link_google") as linked,
    ):
        code = lg.main(["--google-id-token", "not-a-jwt"])

    assert code == 1
    load.assert_not_called()
    linked.assert_not_called()


def test_an_unexpected_error_is_not_swallowed() -> None:
    """The reason the handler names its three types instead of Exception.

    A tidy "FAIL" line for an unanticipated bug would hide it; a traceback
    is the point.
    """
    with (
        patch.object(lg.FirebaseConfig, "load", return_value=_CONFIG),
        patch.object(lg, "link_google", side_effect=RuntimeError("a real bug")),
        pytest.raises(RuntimeError, match="a real bug"),
    ):
        lg.main(["--google-id-token", _google_token()])


def test_the_two_token_sources_are_mutually_exclusive() -> None:
    """Passing both is a user error argparse should catch, not a silent pick."""
    with pytest.raises(SystemExit):
        lg.main(["--google-id-token", "a", "--google-id-token-file", "b"])


def test_one_token_source_is_required() -> None:
    """With neither, there is nothing to link."""
    with pytest.raises(SystemExit):
        lg.main([])
