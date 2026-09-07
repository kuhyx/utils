"""Pushing and pulling the pool, so a day taken on the phone lands on the PC.

Sync is a *separate* operation from every decision in :mod:`freedays._api`.
Nothing that decides whether a gate fires ever waits on this: a gate reads
the last-merged local file and moves on, so an unreachable network makes the
pool stale rather than making a lock hang.

The remote is Firebase RTDB, matching every other app in the fleet, with one
directory per device -- no two devices write the same node, so there is
nothing to conflict and convergence is the CRDT layer's job.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from crdt_sync import (
    ConfigError,
    FileSyncStateStore,
    FirebaseAuthError,
    LogCodec,
    RemoteSyncError,
    RevisionTracking,
    SyncTarget,
    dump_log,
    firebase_client_for,
    load_log,
    sync_log,
)

from freedays._api import actor_id, load, save
from freedays._constants import (
    APP_NAME,
    SYNC_FILENAME,
    SYNC_PATH_PREFIX,
)
from freedays._paths import Paths, resolve_paths

if TYPE_CHECKING:
    from crdt_sync import Log, RemoteStore

_logger = logging.getLogger(__name__)


class SyncUnavailableError(Exception):
    """No usable remote right now -- unconfigured, offline, or rejected.

    Deliberately not a subclass of anything in :mod:`freedays._errors`: this
    is never a policy refusal, and callers treat it the way they treat a
    network timeout.
    """


def get_client() -> RemoteStore:
    """Return a signed-in Firebase client, or raise :class:`SyncUnavailableError`.

    ``ConfigError`` subclasses ``Exception`` directly rather than
    ``RemoteSyncError``, so both are caught explicitly -- assuming one covers
    the other has bitten two other apps in this fleet already.
    """
    try:
        return firebase_client_for(APP_NAME)
    except ConfigError as exc:
        msg = f"free-day sync is not configured on this machine: {exc}"
        raise SyncUnavailableError(msg) from exc
    except FirebaseAuthError as exc:
        msg = f"free-day sync credentials were rejected: {exc}"
        raise SyncUnavailableError(msg) from exc


def sync(
    *,
    client: RemoteStore | None = None,
    paths: Paths | None = None,
) -> Log:
    """Run one pull/merge/push tick and persist the merged pool.

    Args:
        client: Override for the remote; ``None`` builds the Firebase one.
        paths: Where the pool, uuid and sync bookkeeping live.

    Returns:
        The merged pool, as pushed.

    Raises:
        SyncUnavailableError: If no remote could be reached or authenticated.
    """
    resolved = resolve_paths(paths)
    target_client = client if client is not None else get_client()
    node = actor_id(resolved)
    local = load(resolved.log)
    state_path = resolved.sync_state
    try:
        merged = sync_log(
            SyncTarget(
                client=target_client,
                device_id=node,
                path_prefix=SYNC_PATH_PREFIX,
            ),
            local,
            LogCodec(
                encode=dump_log,
                decode=load_log,
                filename=SYNC_FILENAME,
                commit_message="freedays: update pool",
            ),
            RevisionTracking(state_store=FileSyncStateStore(state_path)),
        )
    except RemoteSyncError as exc:
        msg = f"free-day sync could not reach the remote: {exc}"
        raise SyncUnavailableError(msg) from exc
    save(merged, resolved.log)
    return merged


def sync_quietly(*, paths: Paths | None = None) -> bool:
    """Sync, swallowing every failure. Returns whether it actually ran.

    For callers on a timer that want a fresher pool but must not fail, and
    must not say anything, when the sync cannot happen.

    The broad catch is deliberate and is the whole point of this function.
    Today ``FirebaseAuthError`` happens to subclass ``RemoteSyncError`` and
    ``requests``' ``JSONDecodeError`` happens to subclass
    ``RequestException``, so the narrow handler above would in fact catch an
    expired refresh token or a malformed payload. But that is an upstream
    class hierarchy, not a promise to this package -- and a background sync
    whose contract is "never fail" must not have that contract hold only by
    coincidence. Anything unexpected is logged with its traceback, so a real
    bug is loud in the journal while the timer stays green.
    """
    try:
        sync(paths=paths)
    except SyncUnavailableError as exc:
        # The expected case -- offline, or not configured yet. Debug level:
        # this is normal on a laptop and must not fill the journal.
        _logger.debug("free-day sync skipped: %s", exc)
        return False
    except Exception:
        _logger.exception("free-day sync failed unexpectedly")
        return False
    return True
