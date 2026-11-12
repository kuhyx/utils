# Copyright (c) 2026 Krzysztof Rudnicki
"""Encrypted remote store, ``-e2e`` layout and the one-time copy.

Mirrors ``crdt_sync_dart``'s ``EncryptingStore``, ``E2eLayout``,
``copyToEncrypted`` and ``openEncryptedStore`` so Python daemons and Flutter
apps share one encrypted prefix per app.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from crdt_sync._e2e_cache import (
    read_cached_key,
    read_copy_memo,
    write_cached_key,
    write_copy_memo,
)
from crdt_sync._e2e_cipher import E2eDecryptError, open_log_text, seal_log_text
from crdt_sync._e2e_key import (
    Argon2Params,
    E2eHeaderError,
    E2eKey,
    E2eWrongPassphraseError,
    key_matches,
    unlock_e2e,
)
from crdt_sync._log import merge_logs
from crdt_sync._store import dump_log, load_log
from crdt_sync._sync import default_revs_path

if TYPE_CHECKING:
    from pathlib import Path

    from crdt_sync._remote import RemoteStore

_logger = logging.getLogger(__name__)


class E2eLockedError(Exception):
    """No usable key: the caller must not sync at all (fail closed)."""


@dataclass(frozen=True)
class E2eLayout:
    """Where an app's encrypted data lives, derived from its old prefix."""

    prefix: str
    revs_path: str
    e2e_path: str

    @classmethod
    def of(cls, old_prefix: str) -> E2eLayout:
        """Return ``<old>-e2e`` with revs and header kept out of old paths."""
        prefix = f"{old_prefix}-e2e"
        parent, sep, _ = old_prefix.rpartition("/")
        if not sep:
            return cls(prefix, f"{prefix}/revs", f"{prefix}/e2e")
        return cls(prefix, f"{parent}/revs-e2e", f"{parent}/e2e")


class EncryptingStore:
    """Seals log blobs under the layout's prefix and keys its revisions."""

    def __init__(self, inner: RemoteStore, key: E2eKey, layout: E2eLayout) -> None:
        """Wrap ``inner``; other paths pass through unchanged."""
        self._inner = inner
        self.key = key
        self._layout = layout
        self._cipher = key.cipher()

    def _is_rev(self, path: str) -> bool:
        return path.startswith(f"{self._layout.revs_path}/")

    def _is_log(self, path: str) -> bool:
        return (
            not self._is_rev(path)
            and path != self._layout.e2e_path
            and path.startswith(f"{self._layout.prefix}/")
        )

    def list_directory(self, path: str) -> list[str]:
        """Delegate."""
        return self._inner.list_directory(path)

    def get_file_text(self, path: str) -> str | None:
        """Read and open a sealed log; other paths pass through."""
        text = self._inner.get_file_text(path)
        if text is None or not self._is_log(path):
            return text
        return open_log_text(text, self._cipher, path=path)

    def put_file_text(self, path: str, text: str, *, message: str) -> None:
        """Seal logs and key revisions before writing."""
        if self._is_log(path):
            text = seal_log_text(text, self._cipher, path=path)
        elif self._is_rev(path):
            text = self.key.revision(text)
        self._inner.put_file_text(path, text, message=message)

    def get_string_map(self, path: str) -> dict[str, str]:
        """Bulk read; sealed entries come back opened, bad ones dropped."""
        reader = getattr(self._inner, "get_string_map", None)
        if reader is None:
            return {}
        out: dict[str, str] = {}
        for name, value in reader(path).items():
            full = f"{path}/{name}"
            if not self._is_log(full):
                out[name] = value
                continue
            try:
                out[name] = open_log_text(value, self._cipher, path=full)
            except E2eDecryptError:
                _logger.warning("Undecryptable entry %s dropped", full)
        return out

    def delete_file(self, path: str, *, message: str = "") -> None:
        """Delegate."""
        self._inner.delete_file(path, message=message)

    def can_access_remote(self) -> bool:
        """Delegate."""
        return self._inner.can_access_remote()


def _blobs(store: RemoteStore, root: str) -> dict[str, str]:
    """Every text blob under ``root`` (flat leaves and ``<dir>/<file>``)."""
    skip = {default_revs_path(root), f"{root}/e2e", f"{root}/revs"}
    out: dict[str, str] = {}
    for name in store.list_directory(root):
        full = f"{root}/{name}"
        if full in skip:
            continue
        children = store.list_directory(full)
        if not children:
            text = store.get_file_text(full)
            if text is not None:
                out[name] = text
            continue
        for child in children:
            text = store.get_file_text(f"{full}/{child}")
            if text is not None:
                out[f"{name}/{child}"] = text
    return out


def copy_to_encrypted(
    store: RemoteStore, key: E2eKey, old_prefix: str, layout: E2eLayout
) -> int:
    """Merge every readable old log into its encrypted twin; return writes."""
    dest = EncryptingStore(store, key, layout)
    copied = 0
    for rel, text in _blobs(store, old_prefix).items():
        try:
            source = load_log(text)
        except ValueError, KeyError, TypeError:
            _logger.warning("Unreadable old log %s/%s not copied", old_prefix, rel)
            continue
        if not source:
            continue
        path = f"{layout.prefix}/{rel}"
        existing = dest.get_file_text(path)
        try:
            current = load_log(existing) if existing is not None else {}
        except ValueError, KeyError, TypeError:
            # Not a sync log (an app's own blob): never overwrite it.
            _logger.warning("Non-log blob at %s left as is", path)
            continue
        merged = merge_logs(current, source)
        if existing is not None and dump_log(merged) == dump_log(current):
            continue
        dest.put_file_text(path, dump_log(merged), message="e2e copy")
        copied += 1
    return copied


_copied: dict[str, str] = {}


def reset_e2e_copy_memo() -> None:
    """Forget which old prefixes were copied; for tests."""
    _copied.clear()


def _fingerprint(store: RemoteStore, old_prefix: str) -> str:
    reader = getattr(store, "get_string_map", None)
    if reader is None:
        return ""
    revs = reader(default_revs_path(old_prefix))
    return ";".join(f"{k}={revs[k]}" for k in sorted(revs))


@dataclass(frozen=True)
class _OpenRequest:
    old_prefix: str
    layout: E2eLayout
    passphrase: str
    params: Argon2Params | None
    state_dir: Path | None


def _unlock(store: RemoteStore, req: _OpenRequest) -> E2eKey:
    old_prefix, layout, state_dir = req.old_prefix, req.layout, req.state_dir
    if state_dir is not None:
        cached = read_cached_key(state_dir, old_prefix)
        if cached is not None:
            key = E2eKey.from_bytes(cached)
            if key_matches(key, store, layout.e2e_path):
                return key
    if not req.passphrase:
        msg = "no crdt-sync passphrase on this device"
        raise E2eLockedError(msg)
    try:
        key = unlock_e2e(
            store,
            path_prefix=layout.prefix,
            passphrase=req.passphrase,
            params=req.params,
            e2e_path=layout.e2e_path,
        )
    except (E2eWrongPassphraseError, E2eHeaderError) as exc:
        raise E2eLockedError(str(exc) or type(exc).__name__) from exc
    if state_dir is not None:
        write_cached_key(state_dir, old_prefix, key.master)
    return key


def open_encrypted_client(
    store: RemoteStore,
    old_prefix: str,
    *,
    passphrase: str,
    params: Argon2Params | None = None,
    state_dir: Path | None = None,
) -> tuple[EncryptingStore, E2eLayout]:
    """Unlock, copy the old prefix when it changed, and return the store.

    Args:
        store: The outermost remote (above any mirror).
        old_prefix: The app's former plaintext prefix.
        passphrase: The shared crdt-sync password.
        params: Argon2id cost for a header created now; tests lower it.
        state_dir: Where a short-lived daemon keeps its derived key (0600)
            and copy memo between runs; None keeps both in memory only.

    Raises:
        E2eLockedError: No passphrase, a wrong one, or an unreadable header.
    """
    layout = E2eLayout.of(old_prefix)
    key = _unlock(
        store, _OpenRequest(old_prefix, layout, passphrase, params, state_dir)
    )
    fingerprint = _fingerprint(store, old_prefix)
    last = (
        read_copy_memo(state_dir, old_prefix)
        if state_dir is not None
        else _copied.get(old_prefix)
    )
    if last != fingerprint:
        copy_to_encrypted(store, key, old_prefix, layout)
        _copied[old_prefix] = fingerprint
        if state_dir is not None:
            write_copy_memo(state_dir, old_prefix, fingerprint)
    return EncryptingStore(store, key, layout), layout
