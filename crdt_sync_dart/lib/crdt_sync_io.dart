/// Filesystem-backed persistence for `LogStore`.
///
/// Import this instead of (in addition to) `package:crdt_sync/crdt_sync.dart`
/// on platforms with a filesystem (mobile, desktop, server). It pulls in
/// `dart:io`, so it is unavailable on web; the main barrel stays pure Dart.
library;

export 'src/io_store.dart';
