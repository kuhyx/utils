"""Which apps keep a desktop Firebase session, and why the list is hand-kept.

Split out of ``seed_session.py`` for the 250-line cap. The rationale is worth
more than the tuple: it is what stops the next person from "simplifying" this
into a directory scan.
"""

from __future__ import annotations

from typing import Final

# Every app that calls firebase_client_for/mirror_client_for from the desktop,
# and so keeps a refresh token under ~/.config/<app>/. Named here rather than
# discovered from ~/.config: a missing directory is exactly the case that
# needs seeding, so discovery would skip the app that needs this most.
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
# misses call sites passing a constant (wake_alarm._constants.SYNC_APP_NAME,
# home_guard._constants.APP_NAME), so check those by name too. "interop" is
# tool/interop_seed.py's own scratch store, not an app.
DEFAULT_APPS: Final = (
    "diet_guard",
    "wake_alarm",
    "screen_locker",
    "byox_ladder",
    "leetcode_guard",
    "todo",
    "home_guard",
    # The shared free-day pool (~/utils/freedays), not an app: its systemd
    # timer is headless and it has no session of its own to inherit, so
    # without this a day marked on the phone never reaches the PC.
    "freedays",
)
