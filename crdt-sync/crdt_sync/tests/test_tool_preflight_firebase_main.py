"""Tests for ``tool/preflight_firebase``'s loaders and ``main()``.

Split from :mod:`test_tool_preflight_firebase` to stay under the 250-line file
cap; that module covers the individual checks.

The config paths are module-level constants pointing into the real
``~/.config/crdt-sync``, so every test here redirects them at ``tmp_path``
first. Nothing may read or write the user's actual credentials.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
import requests

from tool import preflight_firebase as pf

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_GOOD = {
    "apiKey": "AIzaSyAthisIsTheWebApiKeyFormat",
    "databaseUrl": "https://project-default-rtdb.europe-west1.firebasedatabase.app",
    "projectId": "the-project",
    "uid": "the-uid-pinned-in-the-rules",
    "email": "sync@example.com",
}
_ACCOUNT_PHRASE = "the-sync-account-password"


@pytest.fixture(autouse=True)
def config_dir(tmp_path: Path) -> Iterator[Path]:
    """Point the module's config constants at a throwaway directory.

    Autouse, because a test that forgot this would read -- and report on --
    the real ~/.config/crdt-sync.
    """
    with (
        patch.object(pf, "_CONFIG_FILE", tmp_path / "firebase.json"),
        patch.object(pf, "_PASSWORD_FILE", tmp_path / "password"),
    ):
        yield tmp_path


def _write(directory: Path, config: object = None, password: str | None = None) -> None:
    """Write a config and/or password file into the redirected directory."""
    if config is not None:
        text = config if isinstance(config, str) else json.dumps(config)
        (directory / "firebase.json").write_text(text, encoding="utf-8")
    if password is not None:
        (directory / "password").write_text(password, encoding="utf-8")


def test_a_missing_config_file_is_reported_by_path(config_dir: Path) -> None:
    """The message must name the file, since creating it is the fix."""
    with pytest.raises(pf.PreflightError, match="does not exist"):
        pf._load_config()


def test_invalid_json_is_reported_as_such(config_dir: Path) -> None:
    """A trailing comma is the usual cause and needs naming as a syntax error."""
    _write(config_dir, "{not json,}")

    with pytest.raises(pf.PreflightError, match="not valid JSON"):
        pf._load_config()


def test_a_json_scalar_is_rejected(config_dir: Path) -> None:
    """Valid JSON, wrong shape: the file must hold an object."""
    _write(config_dir, "[]")

    with pytest.raises(pf.PreflightError, match="must contain a JSON object"):
        pf._load_config()


def test_scaffold_comment_keys_are_stripped(config_dir: Path) -> None:
    """They are documentation for whoever fills the file in, not config."""
    _write(config_dir, {**_GOOD, "_comment_apiKey": "where to find this"})

    config = pf._load_config()

    assert config == _GOOD


def test_a_missing_password_file_is_reported_by_path(config_dir: Path) -> None:
    """Absent and empty are the same failure with the same fix."""
    with pytest.raises(pf.PreflightError, match="missing or empty"):
        pf._load_password()


def test_an_empty_password_file_is_reported(config_dir: Path) -> None:
    """A touched-but-unfilled file must not read as a valid empty password."""
    _write(config_dir, password="")

    with pytest.raises(pf.PreflightError, match="missing or empty"):
        pf._load_password()


def test_the_password_is_returned_unstripped(config_dir: Path) -> None:
    """check_shapes is what rejects the newline, so the loader must keep it.

    Stripping here would hide the single most likely hand-editing mistake
    rather than report it.
    """
    _write(config_dir, password=f"{_ACCOUNT_PHRASE}\n")

    assert pf._load_password() == f"{_ACCOUNT_PHRASE}\n"


def test_main_passes_when_every_check_passes(
    config_dir: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The happy path: exit 0, and every check reported by name."""
    _write(config_dir, _GOOD, _ACCOUNT_PHRASE)

    with (
        patch.object(pf, "check_rules_deny_anonymous"),
        patch.object(pf, "check_sign_in_uid_matches"),
        caplog.at_level(logging.INFO, logger="preflight"),
    ):
        code = pf.main()

    assert code == 0
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "PASS  config keys present" in messages
    assert "PASS  sign-in uid matches rules" in messages
    assert "safe to run the migration" in messages


def test_main_returns_1_and_names_the_failing_check(
    config_dir: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A PreflightError is an exit code plus an explanation, not a traceback."""
    _write(config_dir, {**_GOOD, "email": "not-an-address"}, _ACCOUNT_PHRASE)

    with caplog.at_level(logging.INFO, logger="preflight"):
        code = pf.main()

    assert code == 1
    assert "FAIL" in caplog.text
    assert "does not look like an address" in caplog.text


def test_main_stops_at_the_first_failure(config_dir: Path) -> None:
    """Cheapest-first ordering only pays off if it short-circuits.

    A typo must be reported without a network round trip, so the later
    network checks must not run at all.
    """
    _write(config_dir, {**_GOOD, "email": "not-an-address"}, _ACCOUNT_PHRASE)

    with (
        patch.object(pf, "check_rules_deny_anonymous") as rules,
        patch.object(pf, "check_sign_in_uid_matches") as sign_in,
    ):
        code = pf.main()

    assert code == 1
    rules.assert_not_called()
    sign_in.assert_not_called()


def test_main_reports_a_network_failure_distinctly(
    config_dir: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unreachable Firebase is not a misconfiguration; say so."""
    _write(config_dir, _GOOD, _ACCOUNT_PHRASE)

    with (
        patch.object(
            pf,
            "check_rules_deny_anonymous",
            side_effect=requests.ConnectionError("no route to host"),
        ),
        caplog.at_level(logging.INFO, logger="preflight"),
    ):
        code = pf.main()

    assert code == 1
    assert "could not reach Firebase" in caplog.text


def test_main_reports_an_unreadable_config_as_a_failure(
    config_dir: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An OSError reading the files is caught rather than crashing."""
    _write(config_dir, _GOOD, _ACCOUNT_PHRASE)

    with (
        patch.object(pf, "_load_password", side_effect=OSError("permission denied")),
        caplog.at_level(logging.INFO, logger="preflight"),
    ):
        code = pf.main()

    assert code == 1
    assert "could not reach Firebase" in caplog.text


def test_main_runs_the_checks_in_cheapest_first_order(config_dir: Path) -> None:
    """The ordering is the module's stated contract, so pin it."""
    _write(config_dir, _GOOD, _ACCOUNT_PHRASE)
    called: list[str] = []

    with (
        patch.object(pf, "check_keys_present", lambda *_: called.append("keys")),
        patch.object(pf, "check_no_placeholders", lambda *_: called.append("holders")),
        patch.object(pf, "check_shapes", lambda *_: called.append("shapes")),
        patch.object(
            pf, "check_rules_deny_anonymous", lambda *_: called.append("rules")
        ),
        patch.object(pf, "check_sign_in_uid_matches", lambda *_: called.append("uid")),
    ):
        assert pf.main() == 0

    assert called == ["keys", "holders", "shapes", "rules", "uid"]
