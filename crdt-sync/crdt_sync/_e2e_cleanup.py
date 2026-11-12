# Copyright (c) 2026 Krzysztof Rudnicki
"""Clear an app's old plaintext prefix once its encrypted copy is proven.

The migration never deletes the old prefix by itself: an old build may still
write there. Run this once every device runs an encrypting build. It never
creates a header (a typo'd passphrase must not lock the app for good) and
deletes nothing unless every old blob is contained in the encrypted copy.
"""

from __future__ import annotations

import hmac
from typing import TYPE_CHECKING

from crdt_sync._e2e_key import derive_key, read_header
from crdt_sync._e2e_store import E2eLayout, E2eLockedError, EncryptingStore, _blobs
from crdt_sync._log import merge_logs
from crdt_sync._store import dump_log, load_log

if TYPE_CHECKING:
    from crdt_sync._e2e_key import E2eKey
    from crdt_sync._remote import RemoteStore


def unverified_blobs(
    store: RemoteStore, key: E2eKey, old_prefix: str, layout: E2eLayout
) -> list[str]:
    """Return old blobs (relative paths) not fully contained in the copy."""
    dest = EncryptingStore(store, key, layout)
    missing: list[str] = []
    for rel, text in sorted(_blobs(store, old_prefix).items()):
        try:
            source = load_log(text)
            copied = dest.get_file_text(f"{layout.prefix}/{rel}")
            current = load_log(copied) if copied is not None else None
        except ValueError, KeyError, TypeError:
            missing.append(rel)
            continue
        if not source:
            continue
        if current is None or dump_log(merge_logs(current, source)) != dump_log(
            current
        ):
            missing.append(rel)
    return missing


def _existing_key(store: RemoteStore, layout: E2eLayout, passphrase: str) -> E2eKey:
    header = read_header(store, layout.e2e_path)
    if header is None:
        msg = f"no e2e header at {layout.e2e_path}: nothing was migrated"
        raise E2eLockedError(msg)
    key = derive_key(passphrase, header.salt, header.params)
    if not hmac.compare_digest(key.check_for(header.salt), header.check):
        msg = "wrong crdt-sync passphrase"
        raise E2eLockedError(msg)
    return key


def clear_plaintext_prefix(
    store: RemoteStore, old_prefix: str, *, passphrase: str, apply: bool
) -> list[str]:
    """Return the old paths to delete; delete them only when ``apply``.

    Raises:
        E2eLockedError: No header, a wrong passphrase, or a copy that does
            not yet hold every old record.
    """
    layout = E2eLayout.of(old_prefix)
    key = _existing_key(store, layout, passphrase)
    missing = unverified_blobs(store, key, old_prefix, layout)
    if missing:
        msg = f"copy not verified for {', '.join(missing)}"
        raise E2eLockedError(msg)
    paths = [f"{old_prefix}/{rel}" for rel in sorted(_blobs(store, old_prefix))]
    if apply:
        for path in paths:
            store.delete_file(path, message="e2e: clear plaintext prefix")
    return paths
