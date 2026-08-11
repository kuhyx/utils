"""Link a Google identity to the existing sync account, keeping the same uid.

The security rules pin exactly one uid (``auth.uid === '<uid>'``), so signing
in with Google as a *new* account is the one failure this whole feature can
have: authentication succeeds, a different uid comes back, and then every
read and write is denied with no other symptom. The data layer looks broken
while the auth layer looks perfect.

Linking avoids that. ``accounts:signInWithIdp`` called with **both** the
existing account's ``idToken`` and Google's ``id_token`` attaches Google as an
additional provider on the account that already exists, so the uid is
unchanged, the rules need no edit, and every ``<prefix>/<deviceId>/<file>``
path keeps working. Sign in with Google afterwards and the same uid comes
back.

Run once, from the PC, which already holds ``~/.config/crdt-sync/password``.
Obtaining the Google ``id_token`` is a browser flow, so it is passed in rather
than fetched here::

    python3 tool/link_google.py --google-id-token "$(cat token.txt)"
    python3 tool/link_google.py --google-id-token-file token.txt

Exits non-zero, loudly, if the linked account's uid is not the pinned one --
that is the whole point of the script.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import logging
from pathlib import Path
import sys

import requests

from crdt_sync import FirebaseTokenProvider, MemoryCredentialStore
from crdt_sync._config import ConfigError, FirebaseConfig
from crdt_sync._firebase_auth import FirebaseAuthError

_SIGN_IN_BASE = "https://identitytoolkit.googleapis.com/v1"
_TIMEOUT_SECONDS = 30

# A JWT is three dot-separated parts: header, payload, signature. Named so the
# check below reads as intent rather than as a magic number.
_JWT_PART_COUNT = 3

# Matches tool/preflight_firebase.py: these tools report through logging, not
# print, so output is capturable and consistent across the tool/ directory.
_logger = logging.getLogger("link_google")

# Google's ID tokens are issued for the *Web* OAuth client (the audience the
# Android client requests via serverClientId), so this is what should appear
# in the token's `aud` claim. Checked only to make a misconfiguration report
# itself here rather than as an opaque Firebase rejection.
_EXPECTED_ISSUERS = ("https://accounts.google.com", "accounts.google.com")


class LinkError(Exception):
    """The link could not be completed, or completed onto the wrong account."""


def _decode_jwt_claims(token: str) -> dict[str, object]:
    """Return the unverified claims of ``token``.

    Unverified on purpose: this is a local sanity check to produce a good
    error message before spending a network round trip. Firebase verifies the
    signature server-side, and that verification is the one that matters.
    """
    parts = token.split(".")
    if len(parts) != _JWT_PART_COUNT:
        msg = (
            "the --google-id-token value is not a JWT (expected three "
            f"dot-separated parts, got {len(parts)}). Make sure this is the "
            "ID token, not an access token or an authorization code."
        )
        raise LinkError(msg)
    payload = parts[1]
    # JWTs use base64url without padding; add the padding back.
    payload += "=" * (-len(payload) % 4)
    try:
        decoded = json.loads(base64.urlsafe_b64decode(payload))
    except (binascii.Error, ValueError) as exc:
        msg = f"the --google-id-token payload is not valid base64url JSON: {exc}"
        raise LinkError(msg) from exc
    if not isinstance(decoded, dict):
        msg = "the --google-id-token payload is not a JSON object"
        raise LinkError(msg)
    return decoded


def describe_google_token(token: str) -> str:
    """Return a one-line human description of ``token``, validating shape.

    Raises:
        LinkError: If the token is not a Google-issued ID token.
    """
    claims = _decode_jwt_claims(token)
    issuer = str(claims.get("iss", ""))
    if issuer not in _EXPECTED_ISSUERS:
        msg = (
            f"the token was issued by {issuer!r}, not Google. Expected one of "
            f"{_EXPECTED_ISSUERS}."
        )
        raise LinkError(msg)
    email = str(claims.get("email", "<no email claim>"))
    audience = str(claims.get("aud", "<no aud claim>"))
    return f"Google token for {email} (aud={audience})"


def link_google(
    config: FirebaseConfig,
    google_id_token: str,
    *,
    timeout_seconds: float = _TIMEOUT_SECONDS,
) -> str:
    """Link ``google_id_token``'s identity to the configured account.

    Signs in with the stored password first, because linking requires proving
    ownership of the account being linked *to*. Without that ``idToken`` the
    same endpoint happily creates a brand-new account -- the exact silent
    failure this script exists to prevent.

    Args:
        config: The shared Firebase config, already loaded.
        google_id_token: An ID token from Google's OAuth flow.
        timeout_seconds: Per-request network timeout.

    Returns:
        The uid the linked account resolves to.

    Raises:
        LinkError: If Firebase rejects the link, or the resulting uid is not
            the one pinned in the security rules.
    """
    auth = FirebaseTokenProvider(config.api_key, MemoryCredentialStore())
    auth.sign_in(config.email, config.read_password())
    existing_id_token = auth.id_token()

    try:
        response = requests.post(
            f"{_SIGN_IN_BASE}/accounts:signInWithIdp?key={config.api_key}",
            json={
                # idToken names the account to link ONTO. Omitting it turns
                # this call into "sign in or sign up", which would mint a new
                # uid that the security rules reject.
                "idToken": existing_id_token,
                "postBody": f"id_token={google_id_token}&providerId=google.com",
                "requestUri": "http://localhost",
                "returnSecureToken": True,
            },
            timeout=timeout_seconds,
        )
    except requests.RequestException as exc:
        msg = f"network error trying to link the Google account: {exc}"
        raise LinkError(msg) from exc

    if not response.ok:
        msg = (
            f"Firebase rejected the link: HTTP {response.status_code} "
            f"{response.text.strip()}"
        )
        raise LinkError(msg)

    body = response.json()
    linked_uid = str(body.get("localId", ""))
    if not linked_uid:
        msg = f"Firebase returned no localId; body was {body!r}"
        raise LinkError(msg)

    if linked_uid != config.uid:
        msg = (
            f"LINKED THE WRONG ACCOUNT: got uid {linked_uid!r}, but the "
            f"security rules pin {config.uid!r}. Signing in with Google would "
            "authenticate successfully and then be denied every read and "
            "write. Unlink this Google identity in the Firebase console "
            "before retrying."
        )
        raise LinkError(msg)

    return linked_uid


def _read_token(args: argparse.Namespace) -> str:
    if args.google_id_token_file is not None:
        try:
            token = Path(args.google_id_token_file).read_text(encoding="utf-8")
        except OSError as exc:
            msg = f"{args.google_id_token_file} could not be read: {exc}"
            raise LinkError(msg) from exc
    else:
        token = args.google_id_token
    # Strip, because a token pasted through a file or a shell heredoc picks up
    # a trailing newline that Firebase rejects with an unhelpful message.
    token = token.strip()
    if not token:
        msg = "the Google ID token is empty"
        raise LinkError(msg)
    return token


def main(argv: list[str] | None = None) -> int:
    """Link a Google identity to the sync account. Returns an exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--google-id-token",
        help="A Google OAuth ID token (JWT) for the account to link.",
    )
    source.add_argument(
        "--google-id-token-file",
        help="A file containing the Google OAuth ID token.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")

    # ConfigError and FirebaseAuthError are the two non-LinkError failures this
    # path can actually raise (an unusable config file, a rejected password).
    # Caught by name rather than with a bare `except Exception` so an
    # unanticipated bug still surfaces as a traceback instead of a tidy
    # "FAIL" line that hides it.
    try:
        token = _read_token(args)
        _logger.info("  ..  %s", describe_google_token(token))
        config = FirebaseConfig.load()
        _logger.info("  ..  linking onto %s (uid %s)", config.email, config.uid)
        linked_uid = link_google(config, token)
    except (LinkError, ConfigError, FirebaseAuthError):
        # logging.exception already renders the exception and its traceback.
        _logger.exception("  FAIL")
        return 1

    _logger.info("  PASS  Google linked; uid unchanged (%s)", linked_uid)
    _logger.info("")
    _logger.info("Now verify a Google sign-in resolves to the same uid:")
    _logger.info("    python3 tool/preflight_firebase.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
