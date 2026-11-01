# Copyright (c) 2026 Krzysztof Rudnicki
"""Prove Firebase accepts an id_token issued to the stored Desktop OAuth client.

Runs the PKCE loopback flow with the installed-app client (secret included in
the exchange), then calls Firebase Auth REST ``signInWithIdp`` with the result.
The consent click in the browser is the only human step. No app credential
file is written: the session lives in memory and is dropped.

Run from the crdt-sync directory::

    python3 -m tool.verify_desktop_client
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import secrets
import sys
from typing import TYPE_CHECKING

from crdt_sync._autherrors import FirebaseAuthError
from crdt_sync._config import ConfigError, FirebaseConfig
from crdt_sync._credentials import MemoryCredentialStore
from crdt_sync._firebase_auth import FirebaseTokenProvider
from tool._oauth_callback import (
    _CONSENT_TIMEOUT_SECONDS,
    _CallbackHandler,
    _free_port,
    _start_callback_server,
)
from tool._pkce import build_consent_url, make_pkce, open_detached
from tool._token_exchange import TokenError, _authorization_code, _exchange_code
from tool.client_probe import probe_client
from tool.desktop_client import ClientFileError, DesktopClient, load_client

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger("verify_desktop_client")


def audience_of(id_token: str) -> str:
    """Return the ``aud`` claim of an unverified JWT, or ``?`` if unreadable."""
    try:
        segment = id_token.split(".")[1]
        claims = json.loads(
            base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
        )
        return str(claims["aud"])
    except IndexError, ValueError, KeyError, TypeError:
        return "?"


def hint_for(message: str) -> str:
    """Return what to do about a known failure message, or an empty string."""
    if "audience mismatch" in message:
        return (
            "Firebase does not trust this client yet: Firebase console > "
            "Authentication > Sign-in method > Google > Safelist client IDs "
            "from external projects, add the Desktop client id, then rerun."
        )
    if "wrong account" in message:
        return (
            "Pick the sync account in the consent picker (login_hint only "
            "preselects it). Firebase may have created a stray user for the "
            "other account: check Authentication > Users."
        )
    return ""


def fetch_id_token(
    client: DesktopClient,
    login_hint: str,
    *,
    open_browser: bool = True,
    opener: Callable[[str], bool] = open_detached,
) -> str:
    """Run the PKCE loopback flow with ``client`` and return its id_token."""
    port = _free_port()
    redirect_uri = f"http://127.0.0.1:{port}"
    state = secrets.token_urlsafe(16)
    pkce = make_pkce()
    server, thread = _start_callback_server(port, state)
    url = build_consent_url(
        client_id=client.client_id,
        redirect_uri=redirect_uri,
        challenge=pkce.challenge,
        state=state,
        login_hint=login_hint,
    )
    _logger.info("  ..  consent page (opened in your browser, tap Allow):")
    _logger.info("      %s", url)
    if open_browser:
        opener(url)
    thread.join(timeout=_CONSENT_TIMEOUT_SECONDS)
    server.server_close()
    code = _authorization_code(_CallbackHandler.result, redirect_uri, state)
    return _exchange_code(
        code, client.client_id, client.client_secret, redirect_uri, pkce.verifier
    )


def sign_in(config: FirebaseConfig, id_token: str) -> str:
    """Call ``signInWithIdp`` in memory; return the account email.

    Raises:
        FirebaseAuthError: With Firebase's exact message, or on a uid other
            than the pinned one.
    """
    provider = FirebaseTokenProvider(config.api_key, MemoryCredentialStore())
    return provider.sign_in_with_google(id_token, expected_uid=config.uid)


def _fail(message: str) -> int:
    _logger.error("  FAIL  %s", message)
    hint = hint_for(message)
    if hint:
        _logger.error("  ..    %s", hint)
    return 1


def main(argv: list[str] | None = None) -> int:
    """Probe the stored client, run the consent flow, sign in to Firebase."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-browser", action="store_true", help="only print the URL")
    parser.add_argument(
        "--skip-probe", action="store_true", help="skip click-free checks"
    )
    parser.add_argument(
        "--probe-only", action="store_true", help="stop after the click-free checks"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")

    try:
        config = FirebaseConfig.load()
        client = load_client()
        if not args.skip_probe:
            results = probe_client(client)
            for result in results:
                _logger.info("  %s  %s", "ok" if result.ok else "!!", result.detail)
            failed = [r.detail for r in results if not r.ok]
            if failed:
                return _fail("; ".join(failed))
            if args.probe_only:
                return 0
        id_token = fetch_id_token(
            client, config.email, open_browser=not args.no_browser
        )
        _logger.info("  ..  id_token audience: %s", audience_of(id_token))
        email = sign_in(config, id_token)
    except (ConfigError, ClientFileError, TokenError, FirebaseAuthError) as exc:
        return _fail(str(exc))

    _logger.info(
        "  PASS  Firebase accepted the Desktop client: uid %s, %s", config.uid, email
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
