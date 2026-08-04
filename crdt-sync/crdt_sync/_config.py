"""The one place every app learns how to reach Firebase.

Before this module each caller re-read ``~/.config/crdt-sync/firebase.json``
by hand, so a change to the schema meant editing every consumer, and each
consumer got to invent its own half of the credential-cache convention. The
apps share one Firebase project and one account, so they should share one
loader.

Two things live here:

* :class:`FirebaseConfig` -- the parsed, validated config file.
* :func:`firebase_client_for` -- the whole "config file to usable client"
  path, including the per-app credential cache that keeps a fresh process
  from re-authenticating. ``wake_alarm``'s PC side runs every minute and
  ``diet_guard``'s every 15, so caching the refresh token is what makes the
  sign-in cost negligible rather than constant.

Deliberately *not* here: any choice about which backend an app uses. That
stays a constructor change at the call site, per :mod:`crdt_sync._remote`.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import TYPE_CHECKING

from crdt_sync._firebase import FirebaseSyncClient
from crdt_sync._firebase_auth import FileCredentialStore, FirebaseTokenProvider
from crdt_sync._mirror import MirrorSyncClient

if TYPE_CHECKING:
    from crdt_sync._remote import RemoteStore

CONFIG_DIR = Path.home() / ".config" / "crdt-sync"
CONFIG_FILE = CONFIG_DIR / "firebase.json"
PASSWORD_FILE = CONFIG_DIR / "password"

# The scaffold ships "_comment_*" keys explaining where each value comes
# from. They are documentation for a human filling the file in, not config.
_COMMENT_PREFIX = "_comment"


class ConfigError(Exception):
    """The shared Firebase config is missing, malformed or unfilled."""


@dataclass(frozen=True)
class FirebaseConfig:
    """Everything needed to reach the shared Firebase project.

    ``api_key`` is not a secret -- it ships inside the Android APKs, and the
    security rules are what actually protect the data. The password is.
    """

    api_key: str
    database_url: str
    project_id: str
    uid: str
    email: str

    @classmethod
    def load(cls, path: Path | None = None) -> FirebaseConfig:
        """Return the config at ``path``, defaulting to :data:`CONFIG_FILE`.

        Raises:
            ConfigError: If the file is absent, unparsable, missing a key, or
                still holding a scaffold placeholder -- each reported with the
                specific field at fault, because the alternative is a
                confusing auth failure much later.
        """
        source = path if path is not None else CONFIG_FILE
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            msg = f"{source} does not exist; see utils/firebase/README.md"
            raise ConfigError(msg) from exc
        except OSError as exc:
            msg = f"{source} could not be read: {exc}"
            raise ConfigError(msg) from exc
        except ValueError as exc:
            msg = f"{source} is not valid JSON: {exc}"
            raise ConfigError(msg) from exc

        if not isinstance(raw, dict):
            msg = f"{source} must contain a JSON object"
            raise ConfigError(msg)

        data = {k: v for k, v in raw.items() if not k.startswith(_COMMENT_PREFIX)}
        fields = {
            "api_key": "apiKey",
            "database_url": "databaseUrl",
            "project_id": "projectId",
            "uid": "uid",
            "email": "email",
        }
        missing = [key for key in fields.values() if not str(data.get(key, "")).strip()]
        if missing:
            msg = f"{source} is missing or has empty: {', '.join(missing)}"
            raise ConfigError(msg)

        unfilled = [key for key in fields.values() if "PASTE_" in str(data[key])]
        if unfilled:
            msg = f"{source} still holds the placeholder for: {', '.join(unfilled)}"
            raise ConfigError(msg)

        return cls(**{attr: str(data[key]) for attr, key in fields.items()})

    def read_password(self, path: Path | None = None) -> str:
        """Return the sync account's password.

        Stripped, because a text editor that appends a trailing newline would
        otherwise turn into an authentication failure with no visible cause.
        """
        source = path if path is not None else PASSWORD_FILE
        try:
            password = source.read_text(encoding="utf-8").strip()
        except OSError as exc:
            msg = f"{source} could not be read: {exc}"
            raise ConfigError(msg) from exc
        if not password or "PASTE_" in password:
            msg = f"{source} is empty or still holds the scaffold placeholder"
            raise ConfigError(msg)
        return password


def credential_store_for(app_name: str) -> FileCredentialStore:
    """Return the credential cache for ``app_name``.

    Per app rather than shared: two apps signing in as the same account still
    refresh tokens on their own schedules, and a single file written by
    several processes at once is a corruption waiting to happen.
    """
    return FileCredentialStore(
        Path.home() / ".config" / app_name / "firebase_auth.json"
    )


def firebase_client_for(
    app_name: str,
    *,
    config: FirebaseConfig | None = None,
) -> FirebaseSyncClient:
    """Return a signed-in client for ``app_name``.

    Reuses the cached refresh token when there is one and signs in with the
    password only when there is not, so the common path costs no
    authentication round trip at all.

    Args:
        app_name: Names the credential cache, e.g. ``"diet_guard"``.
        config: Overrides the on-disk config; for tests.

    Raises:
        ConfigError: If the shared config is unusable.
        FirebaseAuthError: If the credentials are rejected.
    """
    resolved = config if config is not None else FirebaseConfig.load()
    auth = FirebaseTokenProvider(resolved.api_key, credential_store_for(app_name))
    if not auth.has_session():
        auth.sign_in(resolved.email, resolved.read_password())
    return FirebaseSyncClient(resolved.database_url, auth)


def mirror_client_for(
    app_name: str,
    github_client: RemoteStore,
    *,
    config: FirebaseConfig | None = None,
) -> MirrorSyncClient:
    """Return a Firebase-primary client that still mirrors to ``github_client``.

    This is what an app uses *during* the cutover. Firebase is authoritative,
    so its failures fail the tick; GitHub is kept in step but never allowed
    to. Reads union both, which is what lets devices cut over one at a time
    without a migrated PC losing sight of an un-migrated phone.

    Rolling back is deleting the call: pass the GitHub client straight to
    :func:`crdt_sync.sync_log` again. Retiring the mirror is swapping this for
    :func:`firebase_client_for`. Both are one-line changes at the call site,
    which is the whole point of the :class:`~crdt_sync.RemoteStore` seam.

    Args:
        app_name: Names the credential cache, e.g. ``"diet_guard"``.
        github_client: The existing GitHub client, kept as the fallback.
        config: Overrides the on-disk config; for tests.
    """
    return MirrorSyncClient(
        primary=firebase_client_for(app_name, config=config),
        mirror=github_client,
    )
