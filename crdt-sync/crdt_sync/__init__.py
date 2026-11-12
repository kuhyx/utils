# Copyright (c) 2026 Krzysztof Rudnicki
"""Shared CRDT merge scheme + pluggable remote sync transports."""

from __future__ import annotations

from crdt_sync._config import (
    CONFIG_DIR,
    CONFIG_FILE,
    PASSWORD_FILE,
    ConfigError,
    FirebaseConfig,
    credential_store_for,
    firebase_client_for,
    mirror_client_for,
)
from crdt_sync._device import DeviceIdentity, load_device_identity
from crdt_sync._e2e_cipher import (
    E2eCipher,
    E2eDecryptError,
    is_e2e_envelope,
    open_log_text,
    seal_log_text,
)
from crdt_sync._e2e_key import (
    Argon2Params,
    E2eHeaderError,
    E2eKey,
    E2eWrongPassphraseError,
    default_e2e_path,
    unlock_e2e,
)
from crdt_sync._e2e_store import (
    E2eLayout,
    E2eLockedError,
    EncryptingStore,
    copy_to_encrypted,
    open_encrypted_client,
    reset_e2e_copy_memo,
)
from crdt_sync._firebase import (
    DatabaseNotFoundError,
    FirebaseSyncClient,
    FirebaseSyncError,
)
from crdt_sync._firebase_auth import (
    CredentialStore,
    FileCredentialStore,
    FirebaseAuthError,
    FirebaseCredentials,
    FirebaseTokenProvider,
    MemoryCredentialStore,
)
from crdt_sync._github import GitHubSyncClient, GitHubSyncError, RepoNotFoundError
from crdt_sync._hlc import Hlc
from crdt_sync._log import Log, merge_logs
from crdt_sync._mirror import MirrorSyncClient
from crdt_sync._record import Field, Record, merge_field, merge_record
from crdt_sync._remote import RemoteNotFoundError, RemoteStore, RemoteSyncError
from crdt_sync._store import dump_log, load_log, read_log, write_log
from crdt_sync._sync import (
    FileSyncStateStore,
    LogCodec,
    MemorySyncStateStore,
    RevisionTracking,
    SyncState,
    SyncStateStore,
    SyncTarget,
    default_revs_path,
    revision_of,
    sync_log,
)

__all__ = [
    "CONFIG_DIR",
    "CONFIG_FILE",
    "PASSWORD_FILE",
    "Argon2Params",
    "ConfigError",
    "CredentialStore",
    "DatabaseNotFoundError",
    "DeviceIdentity",
    "E2eCipher",
    "E2eDecryptError",
    "E2eHeaderError",
    "E2eKey",
    "E2eLayout",
    "E2eLockedError",
    "E2eWrongPassphraseError",
    "EncryptingStore",
    "Field",
    "FileCredentialStore",
    "FileSyncStateStore",
    "FirebaseAuthError",
    "FirebaseConfig",
    "FirebaseCredentials",
    "FirebaseSyncClient",
    "FirebaseSyncError",
    "FirebaseTokenProvider",
    "GitHubSyncClient",
    "GitHubSyncError",
    "Hlc",
    "Log",
    "LogCodec",
    "MemoryCredentialStore",
    "MemorySyncStateStore",
    "MirrorSyncClient",
    "Record",
    "RemoteNotFoundError",
    "RemoteStore",
    "RemoteSyncError",
    "RepoNotFoundError",
    "RevisionTracking",
    "SyncState",
    "SyncStateStore",
    "SyncTarget",
    "copy_to_encrypted",
    "credential_store_for",
    "default_e2e_path",
    "default_revs_path",
    "dump_log",
    "firebase_client_for",
    "is_e2e_envelope",
    "load_device_identity",
    "load_log",
    "merge_field",
    "merge_logs",
    "merge_record",
    "mirror_client_for",
    "open_encrypted_client",
    "open_log_text",
    "read_log",
    "reset_e2e_copy_memo",
    "revision_of",
    "seal_log_text",
    "sync_log",
    "unlock_e2e",
    "write_log",
]
