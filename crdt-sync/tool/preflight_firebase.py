"""Validate ``~/.config/crdt-sync`` before anything is migrated.

Every failure this catches is one that would otherwise surface *after* data
had started moving, when it is expensive: a placeholder left unreplaced, a
database URL with a trailing slash, a password saved with the trailing
newline a text editor adds, or -- the worst one -- an account whose uid is not
the uid pinned in the security rules, which denies every read and write with
no other symptom.

Checks are ordered cheapest-first and stop at the first failure, so a typo is
reported without a network round trip.

Usage::

    python3 tool/preflight_firebase.py

Prints a PASS/FAIL line per check and exits non-zero if any failed. Reads
only; it writes nothing, locally or remotely.
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
import sys

import requests

from crdt_sync import FirebaseTokenProvider, MemoryCredentialStore

_CONFIG_DIR = Path.home() / ".config" / "crdt-sync"
_CONFIG_FILE = _CONFIG_DIR / "firebase.json"
_PASSWORD_FILE = _CONFIG_DIR / "password"
_REQUIRED_KEYS = ("apiKey", "databaseUrl", "projectId", "uid", "email")
_TIMEOUT_SECONDS = 30

_logger = logging.getLogger("preflight")


class PreflightError(Exception):
    """A configuration problem that must be fixed before migrating."""


def _load_config() -> dict[str, str]:
    """Return the parsed config, or raise with a fixable message."""
    if not _CONFIG_FILE.is_file():
        msg = f"{_CONFIG_FILE} does not exist"
        raise PreflightError(msg)
    try:
        data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except ValueError as exc:
        msg = f"{_CONFIG_FILE} is not valid JSON: {exc}"
        raise PreflightError(msg) from exc
    if not isinstance(data, dict):
        msg = f"{_CONFIG_FILE} must contain a JSON object"
        raise PreflightError(msg)
    # The scaffold ships explanatory "_comment_*" keys; they are documentation
    # for whoever fills the file in, not configuration.
    return {k: v for k, v in data.items() if not k.startswith("_comment")}


def _load_password() -> str:
    """Return the sync account's password, or raise with a fixable message."""
    password = (
        _PASSWORD_FILE.read_text(encoding="utf-8") if _PASSWORD_FILE.is_file() else ""
    )
    if not password:
        msg = f"{_PASSWORD_FILE} is missing or empty"
        raise PreflightError(msg)
    return password


def check_keys_present(config: dict[str, str]) -> None:
    """Every required key exists and is a non-empty string."""
    missing = [k for k in _REQUIRED_KEYS if not str(config.get(k, "")).strip()]
    if missing:
        msg = f"missing or empty in firebase.json: {', '.join(missing)}"
        raise PreflightError(msg)


def check_no_placeholders(config: dict[str, str], password: str) -> None:
    """No scaffold placeholder survived into a real value."""
    unfilled = [k for k, v in config.items() if "PASTE_" in str(v)]
    if "PASTE_" in password:
        unfilled.append("password (the password file)")
    if unfilled:
        msg = f"still holding the scaffold placeholder: {', '.join(unfilled)}"
        raise PreflightError(msg)


def check_shapes(config: dict[str, str], password: str) -> None:
    """Values look like what they claim to be.

    A trailing slash on ``databaseUrl`` yields a double slash in every request
    path, and a trailing newline on the password is the single most likely
    hand-editing mistake -- both produce confusing auth or 404 errors much
    later.
    """
    url = config["databaseUrl"]
    if not url.startswith("https://"):
        msg = f"databaseUrl must start with https:// -- got {url!r}"
        raise PreflightError(msg)
    if url.endswith("/"):
        msg = f"databaseUrl must not end with '/' -- got {url!r}"
        raise PreflightError(msg)
    if not config["apiKey"].startswith("AIza"):
        msg = "apiKey does not start with 'AIza'; that is the Web API key format"
        raise PreflightError(msg)
    if password != password.strip():
        msg = "the password file has leading/trailing whitespace (likely a newline)"
        raise PreflightError(msg)
    if "@" not in config["email"]:
        msg = f"email does not look like an address -- got {config['email']!r}"
        raise PreflightError(msg)


def check_rules_deny_anonymous(config: dict[str, str]) -> None:
    """The URL names a real database, and an anonymous read is refused.

    Both failures look alike from a distance and are worth separating. A
    wrong-region URL answers 404 with a ``correctUrl`` body rather than an
    error a caller would notice, so it would otherwise sail past this check,
    pass sign-in (a different host entirely) and only break once the
    migration started writing.
    """
    response = requests.get(f"{config['databaseUrl']}/.json", timeout=_TIMEOUT_SECONDS)

    if response.status_code == requests.codes.not_found:
        try:
            correct = response.json().get("correctUrl")
        except ValueError:
            correct = None
        if correct:
            msg = f"databaseUrl is for the wrong region; use {correct!r}"
            raise PreflightError(msg)
        msg = (
            f"{config['databaseUrl']} returned 404 -- no database lives there. "
            "Check the URL against Realtime Database > Data in the console."
        )
        raise PreflightError(msg)

    if response.status_code == requests.codes.ok:
        msg = (
            "UNAUTHENTICATED READ SUCCEEDED -- the database is world-readable. "
            "Publish database.rules.json before migrating anything."
        )
        raise PreflightError(msg)


def check_sign_in_uid_matches(config: dict[str, str], password: str) -> None:
    """Sign-in works and returns exactly the uid pinned in the rules.

    The decisive check. A different uid authenticates fine and then fails
    every single read and write with a bare permission error.
    """
    auth = FirebaseTokenProvider(config["apiKey"], MemoryCredentialStore())
    # Raises FirebaseAuthError on bad credentials, or if Email/Password
    # sign-in is disabled for the project.
    auth.sign_in(config["email"], password)

    # sign_in() returns None and keeps only the tokens, so read the uid back
    # out of the ID token itself. The token is a JWT whose payload carries the
    # subject; decoding it needs no verification here, because the value is
    # only being compared against the local config, not trusted for access.
    payload = auth.id_token().split(".")[1]
    padded = payload + "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(padded))
    actual = claims.get("user_id") or claims.get("sub")

    if actual != config["uid"]:
        msg = (
            f"signed in as uid {actual!r} but the rules pin {config['uid']!r} -- "
            "every read and write would be denied"
        )
        raise PreflightError(msg)


def main() -> int:
    """Run every check, returning a process exit code."""
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    try:
        config = _load_config()
        password = _load_password()

        checks = (
            ("config keys present", lambda: check_keys_present(config)),
            ("no placeholders left", lambda: check_no_placeholders(config, password)),
            ("values well-formed", lambda: check_shapes(config, password)),
            ("rules deny anonymous reads", lambda: check_rules_deny_anonymous(config)),
            (
                "sign-in uid matches rules",
                lambda: check_sign_in_uid_matches(config, password),
            ),
        )
        for name, run in checks:
            run()
            _logger.info("  PASS  %s", name)
    except PreflightError as exc:
        _logger.info("  FAIL  %s", exc)
        return 1
    except (requests.RequestException, OSError) as exc:
        _logger.info("  FAIL  could not reach Firebase: %s", exc)
        return 1

    _logger.info("\nAll preflight checks passed; safe to run the migration.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
