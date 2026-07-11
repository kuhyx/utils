import 'dart:io';

import 'store.dart';

/// A [LogPersistence] backed by a single JSON file.
///
/// Writes atomically -- to a per-process temp file, then `rename`d over the
/// real path -- so a concurrent reader (e.g. a background sync isolate writing
/// while the foreground app also writes) never observes a half-written file.
/// The pid in the temp name keeps two writers from colliding. This generalizes
/// diet_guard's hand-rolled `LogStorageService` write scheme.
///
/// Lives behind the `package:crdt_sync/crdt_sync_io.dart` entrypoint, not the
/// main barrel, because it imports `dart:io` and so is unavailable on web --
/// the core [LogStore] stays pure Dart.
class FileLogPersistence implements LogPersistence {
  /// Persists to [file]. The app chooses the path (e.g. via `path_provider`);
  /// the library takes no dependency on where app documents live.
  FileLogPersistence(this._file);

  final File _file;

  @override
  Future<String?> read() async {
    if (!_file.existsSync()) return null;
    try {
      return await _file.readAsString();
    } on FileSystemException {
      return null;
    }
  }

  @override
  Future<void> write(String text) async {
    await _file.parent.create(recursive: true);
    final tmp = File('${_file.path}.$pid.tmp');
    await tmp.writeAsString(text);
    await tmp.rename(_file.path);
  }
}
