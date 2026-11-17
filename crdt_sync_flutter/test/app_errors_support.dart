/// Shared pieces of the app-errors tests: the RTDB sink fake and a config.
library;

import 'package:crdt_sync_flutter/crdt_sync_flutter.dart';

/// A sink recording every patch; [fail] makes the next ones throw.
class FakeSink {
  final patches = <String, Map<String, Object?>>{};
  bool fail = false;

  Future<void> call(String path, Map<String, Object?> values) async {
    if (fail) throw StateError('offline');
    (patches[path] ??= {}).addAll(values);
  }

  List<Map<String, Object?>> get entries => [
    for (final v in patches.values.expand((m) => m.values))
      v! as Map<String, Object?>,
  ];
}

const config = AppErrorsConfig(
  app: 'todo',
  repo: 'kuhyx/todo',
  build: 42,
  version: '1.2.3',
);

/// An error whose toString throws.
class ThrowingToString {
  @override
  String toString() => throw StateError('no');
}
