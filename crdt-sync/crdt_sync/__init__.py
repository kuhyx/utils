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
    MemorySyncStateStore,
    SyncState,
    SyncStateStore,
    default_revs_path,
    revision_of,
    sync_log,
)

__all__ = [
    "CONFIG_DIR",
    "CONFIG_FILE",
    "PASSWORD_FILE",
    "ConfigError",
    "CredentialStore",
    "DatabaseNotFoundError",
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
    "MemoryCredentialStore",
    "MemorySyncStateStore",
    "MirrorSyncClient",
    "Record",
    "RemoteNotFoundError",
    "RemoteStore",
    "RemoteSyncError",
    "RepoNotFoundError",
    "SyncState",
    "SyncStateStore",
    "credential_store_for",
    "default_revs_path",
    "dump_log",
    "firebase_client_for",
    "load_log",
    "merge_field",
    "merge_logs",
    "merge_record",
    "mirror_client_for",
    "read_log",
    "revision_of",
    "sync_log",
    "write_log",
]
