r"""Reseed each app's desktop Firebase session by signing in with Google.

The sync account moved to Google-only sign-in, so the password flow that used
to fill ``~/.config/<app>/firebase_auth.json`` no longer works and every
desktop refresh token eventually expires. Headless jobs (systemd timers, the
sync CLIs) cannot run a browser flow themselves, so this runs it once,
interactively, and stores the refresh token each app then lives on.

Deliberately *not* a service-account key. That authenticates as an admin and
bypasses the security rules, so the pinned-uid rule protecting this data would
stop applying to every PC write.

Run from the repo root, as a module -- ``python3 tool/seed_session.py`` fails
with ``No module named 'tool'``, because that puts ``tool/`` on the path
instead of the root this imports ``tool.google_id_token`` from::

    python3 -m tool.seed_session --client-id <web-client-id> \\
        --client-secret <web-client-secret>

    # Reseed a subset instead of every app:
    python3 -m tool.seed_session --client-id ... --client-secret ... \\
        --app diet_guard --app wake_alarm

One consent tap covers every app: the Google ID token is fetched once and
exchanged once per app, because ``credential_store_for`` keeps a separate file
per app on purpose (independent refresh schedules, no concurrent writers).

The client id and secret come from the **Web application** OAuth client in the
project's Google Cloud console -- the same pair ``google_id_token.py`` takes.
"""

from __future__ import annotations

import argparse
import logging
import sys

from crdt_sync._config import ConfigError, FirebaseConfig, credential_store_for
from crdt_sync._firebase import FirebaseSyncClient
from crdt_sync._firebase_auth import FirebaseAuthError, FirebaseTokenProvider
from crdt_sync._remote import RemoteSyncError

# Importable as a package module (tool/__init__.py exists) so the loopback
# OAuth flow is shared rather than reimplemented.
from tool.google_id_token import TokenError, fetch_id_token

# Every app that calls firebase_client_for/mirror_client_for from the desktop,
# and so keeps a refresh token under ~/.config/<app>/. Named here rather than
# discovered from ~/.config, because a missing directory is exactly the case
# that needs seeding -- discovery would skip the app that needs this most.
#
# The remaining Flutter-only apps (home_inventory, workout_app) are absent on
# purpose: they authenticate in-app on the phone and have no desktop session.
# `todo` used to be grouped with them, but it grew a real desktop wrapper
# (lib/desktop/wrapper_server.dart) with its own Firebase REST client that
# needs a session exactly like the Python daemons do -- see
# lib/sync/firebase_backend.dart and lib/desktop/wrapper_server.dart in
# ~/todo. Its credential cache lives at ~/.config/todo/firebase_auth.json,
# same shape as every entry below, even though the reader is Dart, not
# Python: FirebaseCredentials.fromJson in crdt_sync_dart parses the exact
# {id_token, refresh_token, expires_at} shape credential_store_for writes.
#
# Re-derive rather than guess when adding one; a repo-by-repo sweep missed two
# of these. Grep all of ~ for the string literal passed to firebase_client_for,
# mirror_client_for and credential_store_for across every *.py. That still
# misses call sites passing a constant -- wake_alarm goes through
# wake_alarm._constants.SYNC_APP_NAME -- so check those by name too. "interop"
# is tool/interop_seed.py's own scratch store, not an app.
DEFAULT_APPS = (
    "diet_guard",
    "wake_alarm",
    "screen_locker",
    "byox_ladder",
    "leetcode_guard",
    "todo",
)

# A fixed default so the redirect URI is stable enough to register once on the
# Web client. Arbitrary but out of the ephemeral range, and free on this box.
_DEFAULT_REDIRECT_PORT = 8765

_logger = logging.getLogger("seed_session")


class SeedError(Exception):
    """A session was stored but could not actually reach the database.

    Carries the apps already finished when it was raised, so a partially
    completed run can report what is left rather than leaving the state to be
    reconstructed by hand.
    """

    def __init__(self, message: str, done: tuple[str, ...] = ()) -> None:
        """Record ``message`` and the apps that verified before the failure."""
        super().__init__(message)
        self.done = done


def seed_apps(
    config: FirebaseConfig,
    google_id_token: str,
    app_names: tuple[str, ...],
) -> list[str]:
    """Store a Google-backed session for each app. Returns the apps seeded.

    Each app gets its own exchange because each has its own credential file;
    a single session copied across them would have them all refreshing the
    same rotated token and invalidating each other.

    Each session is then proved with a real authenticated read, because a
    written credential file is not evidence of working sync: the whole reason
    this script exists is that the files were present and the tokens dead.
    Firebase may also invalidate an earlier refresh token when a new session
    is minted for the same uid, which would leave every app but the last one
    broken -- a failure only a per-app read can see.

    Args:
        config: The shared Firebase config, already loaded.
        google_id_token: An ID token from Google's OAuth flow.
        app_names: The apps whose credential caches to fill.

    Returns:
        The app names seeded, in the order given.

    Raises:
        FirebaseAuthError: If Firebase rejects the token, or it resolves to a
            uid other than the pinned one. Raised on the first failure, so a
            wrong account cannot be written to any app.
        SeedError: If a seeded session cannot actually read the database.
    """
    seeded: list[str] = []
    for app_name in app_names:
        provider = FirebaseTokenProvider(
            config.api_key,
            credential_store_for(app_name),
        )
        email = provider.sign_in_with_google(
            google_id_token,
            expected_uid=config.uid,
        )
        seeded.append(app_name)
        _logger.info("  ..  %s seeded as %s", app_name, email or config.email)

    # Verified in a second pass, after every session exists: checking each one
    # as it is written would pass an app that a later exchange then
    # invalidates, which is precisely the failure being guarded against.
    verified: list[str] = []
    for app_name in seeded:
        client = FirebaseSyncClient(
            config.database_url,
            FirebaseTokenProvider(config.api_key, credential_store_for(app_name)),
        )
        # list_directory rather than can_access_remote(): the latter collapses
        # rules-denied, dead-token and network-down into one False, and a gate
        # whose whole job is saying what broke should not throw that away.
        # Both read the database root, which is where the rules grant .read.
        try:
            client.list_directory("")
        except (RemoteSyncError, FirebaseAuthError) as exc:
            msg = (
                f"{app_name} was seeded but cannot read the database ({exc}). "
                "Its session is not usable, so sync would keep failing "
                "silently."
            )
            raise SeedError(msg, tuple(verified)) from exc
        verified.append(app_name)
        _logger.info("  ..  %s verified: authenticated read succeeded", app_name)
    return verified


def main(argv: list[str] | None = None) -> int:
    """Run the consent flow and seed every app. Returns an exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--client-id", required=True, help="Web OAuth client id.")
    parser.add_argument(
        "--client-secret",
        required=True,
        help="Web OAuth client secret.",
    )
    parser.add_argument(
        "--app",
        action="append",
        dest="apps",
        # Constrained rather than free-form: a typo like "diet-guard" would
        # otherwise create ~/.config/diet-guard/, verify against it happily,
        # and report PASS while the real diet_guard stayed dead. The stray
        # directories already in ~/.config are what that looks like.
        choices=DEFAULT_APPS,
        help=(
            "Seed only this app; repeatable. Defaults to all of: "
            + ", ".join(DEFAULT_APPS)
        ),
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Print the consent URL without launching a browser.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=_DEFAULT_REDIRECT_PORT,
        help=(
            "Loopback port for the OAuth redirect. Must be registered on the "
            "Web client as http://localhost:<port>, exactly -- a Web client "
            "does not accept arbitrary loopback ports the way a Desktop "
            "client does."
        ),
    )
    args = parser.parse_args(argv)
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")

    app_names = tuple(args.apps) if args.apps else DEFAULT_APPS

    # Caught by name rather than with a bare `except Exception` so an
    # unanticipated bug still surfaces as a traceback instead of a tidy
    # "FAIL" line that hides it.
    try:
        config = FirebaseConfig.load()
        _logger.info("  ..  seeding %s", ", ".join(app_names))
        _logger.info("  ..  expecting uid %s (%s)", config.uid, config.email)
        token = fetch_id_token(
            args.client_id,
            args.client_secret,
            open_browser=not args.no_browser,
            port=args.port,
        )
        seeded = seed_apps(config, token, app_names)
    except (ConfigError, FirebaseAuthError, TokenError, SeedError) as exc:
        # logging.exception already renders the exception and its traceback.
        _logger.exception("  FAIL")
        # A run that dies partway leaves some apps working and some not.
        # Saying which is the difference between rerunning the ones that need
        # it and a hunt through ~/.config for what actually happened.
        done = exc.done if isinstance(exc, SeedError) else ()
        remaining = [name for name in app_names if name not in done]
        if done:
            _logger.exception("  ..  already working: %s", ", ".join(done))
        _logger.exception(
            "  ..  rerun with: %s",
            " ".join(f"--app {name}" for name in remaining),
        )
        return 1

    _logger.info("  PASS  %d desktop session(s) seeded and read-verified", len(seeded))
    return 0


if __name__ == "__main__":
    sys.exit(main())
