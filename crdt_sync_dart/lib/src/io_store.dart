import 'dart:io';
import 'dart:math';

import 'store.dart';

/// A [LogPersistence] backed by a single JSON file.
///
/// Writes atomically -- to a per-process temp file, then `rename`d over the
/// real path -- so a concurrent reader (e.g. a background sync isolate writing
/// while the foreground app also writes) never observes a half-written file.
/// The pid plus a random per-instance token in the temp name keep two
/// writers from colliding: two processes, and two instances in one process
/// (a Flutter app's UI engine and a headless engine share a pid -- wake_alarm
/// lost a publish to exactly that, 2026-11-22). Within one instance, writes
/// are serialized in issue order (last issued wins), so overlapping calls
/// (e.g. per-keystroke saves) never share the temp file mid-flight. This generalizes diet_guard's hand-rolled `LogStorageService`
/// write scheme.
///
/// Lives behind the `package:crdt_sync/crdt_sync_io.dart` entrypoint, not the
/// main barrel, because it imports `dart:io` and so is unavailable on web --
/// the core [LogStore] stays pure Dart.
class FileLogPersistence implements LogPersistence {
  /// Persists to [file]. The app chooses the path (e.g. via `path_provider`);
  /// the library takes no dependency on where app documents live.
  FileLogPersistence(this._file)
    : _token = Random.secure().nextInt(1 << 32).toRadixString(36);

  final File _file;

  /// Tells this instance's temp file apart from another's in this process.
  final String _token;

  /// Completes when the most recently issued write has settled. Never
  /// rejects, so one failed write cannot block the ones queued after it.
  Future<void> _tail = Future<void>.value();

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
  Future<void> write(String text) {
    final result = _tail.then((_) => _writeNow(text));
    // The caller still sees its own error via [result]; the chain ignores it.
    _tail = result.then((_) {}, onError: (Object _) {});
    return result;
  }

  Future<void> _writeNow(String text) async {
    await _file.parent.create(recursive: true);
    final tmp = File('${_file.path}.$pid.$_token.tmp');
    await tmp.writeAsString(text);
    await tmp.rename(_file.path);
  }
}
