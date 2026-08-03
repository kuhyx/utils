/// Raised for a remote-storage failure the caller must not silently ignore.
///
/// The backend-neutral base of the error hierarchy: catch this to handle
/// "the sync transport failed" regardless of which backend is configured.
/// Backends narrow it -- `GitHubSyncError` and `FirebaseSyncError` both
/// extend it -- so existing `on GitHubSyncError` catches keep working while a
/// caller that has been migrated can catch the base type instead.
class RemoteSyncError implements Exception {
  RemoteSyncError(this.message);

  final String message;

  // Uses runtimeType so subclasses read as themselves without each having to
  // override toString.
  @override
  String toString() => '$runtimeType: $message';
}

/// Raised when the configured remote itself is unreachable.
///
/// Distinguished from a missing *path* (nothing pushed there yet, which is
/// benign -- it just means no other device has synced before) so the caller
/// can tell "the repo/database is wrong or the credential isn't scoped to it"
/// apart from "no other device has synced yet".
class RemoteNotFoundError extends RemoteSyncError {
  RemoteNotFoundError(super.message);
}

/// The whole remote surface `crdt_sync` syncs through: dumb keyed storage of
/// UTF-8 text blobs, with directory listing.
///
/// Deliberately tiny. `syncLog` and every app-level sync service talk only to
/// this, so swapping the storage backend (GitHub Contents API, Firebase
/// Realtime Database, a dual-writing mirror of both) is a constructor change
/// at the call site and nothing more.
///
/// Implementations are expected to throw [RemoteSyncError] (or a subclass) for
/// any failure the caller must not silently ignore, and to treat a missing
/// path as a benign `null` / empty rather than an error.
abstract interface class RemoteStore {
  /// Returns the entry names directly under [path], or an empty list when
  /// nothing has been written there yet.
  ///
  /// Includes both files and subdirectories: the
  /// `<pathPrefix>/<deviceId>/<filename>` layout needs to discover device
  /// *directories*, not just files.
  Future<List<String>> listDirectory(String path);

  /// Returns the text stored at [path], or null when nothing is there yet.
  Future<String?> getFileText(String path);

  /// Creates or replaces the text at [path].
  ///
  /// [message] is a human-readable reason for the write. Backends that record
  /// one (GitHub commits) use it; backends that don't (Firebase) ignore it.
  Future<void> putFileText(String path, String text, {required String message});

  /// Deletes [path]. A no-op when [path] does not exist.
  Future<void> deleteFile(String path, {String message});

  /// Returns whether the configured credential can reach the remote.
  ///
  /// A lightweight connection test for a settings "Test connection" button: it
  /// probes the remote root, so it succeeds even before any file has been
  /// pushed. Never throws -- a network failure or missing remote returns
  /// false.
  Future<bool> canAccessRemote();

  /// Releases the underlying HTTP client.
  void close();
}

/// Optional capability: read a whole small map of text values in one request.
///
/// Implemented by backends where that is a single cheap call
/// (`FirebaseRestClient`), and absent where it would be one request per key
/// (`GitHubClient`). [syncLog] uses it to fetch every peer's revision in one
/// go and skip downloading logs that have not changed -- the difference
/// between a sync tick costing a few hundred bytes and a few hundred
/// kilobytes. A backend that does not implement it simply syncs the old way.
abstract interface class BulkMapReader {
  /// Returns the map at [path] as `key -> text`, empty when absent.
  ///
  /// Never throws for a malformed or missing value: this backs an
  /// *optimisation*, and a corrupt map must degrade into "fetch everything",
  /// never into a failed sync.
  Future<Map<String, String>> getStringMap(String path);
}
