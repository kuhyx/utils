import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';

const cheapArgon = Argon2Params(memoryKiB: 8, iterations: 1, parallelism: 1);

Log logOf(Map<String, String> titles, {String nodeId = 'node-a'}) => {
  for (final entry in titles.entries)
    entry.key: Record(
      id: entry.key,
      fields: {
        'title': (
          entry.value,
          Hlc(wallTimeMs: 1000, counter: 0, nodeId: nodeId),
        ),
      },
    ),
};

String encodeLog(Log log) =>
    jsonEncode(log.map((id, record) => MapEntry(id, record.toJson())));

Log decodeLog(String text) => (jsonDecode(text) as Map<String, dynamic>).map(
  (id, data) => MapEntry(id, Record.fromJson(data as Map<String, dynamic>)),
);

/// In-memory remote; [bulk] toggles the [BulkMapReader] capability.
class MemoryRemote implements RemoteStore, BulkMapReader {
  MemoryRemote([Map<String, String>? files]) : files = files ?? {};

  final Map<String, String> files;
  final List<String> writes = [];
  final List<String> reads = [];
  bool closed = false;

  /// Overrides the next reads of a path, oldest first, to fake a race.
  final Map<String, List<String?>> scriptedReads = {};

  @override
  Future<List<String>> listDirectory(String path) async => files.keys
      .where((key) => key.startsWith('$path/'))
      .map((key) => key.substring(path.length + 1).split('/').first)
      .toSet()
      .toList();

  @override
  Future<String?> getFileText(String path) async {
    reads.add(path);
    final script = scriptedReads[path];
    if (script != null && script.isNotEmpty) return script.removeAt(0);
    return files[path];
  }

  @override
  Future<void> putFileText(
    String path,
    String text, {
    required String message,
  }) async {
    writes.add(path);
    files[path] = text;
  }

  @override
  Future<Map<String, String>> getStringMap(String path) async => {
    for (final entry in files.entries)
      if (entry.key.startsWith('$path/'))
        entry.key.substring(path.length + 1): entry.value,
  };

  @override
  Future<void> deleteFile(String path, {String message = ''}) async =>
      files.remove(path);

  @override
  Future<bool> canAccessRemote() async => true;

  @override
  void close() => closed = true;
}

/// Same storage without the bulk capability, like `GitHubClient`.
class PlainRemote implements RemoteStore {
  PlainRemote(this.inner);

  final MemoryRemote inner;

  @override
  Future<List<String>> listDirectory(String path) => inner.listDirectory(path);

  @override
  Future<String?> getFileText(String path) => inner.getFileText(path);

  @override
  Future<void> putFileText(
    String path,
    String text, {
    required String message,
  }) => inner.putFileText(path, text, message: message);

  @override
  Future<void> deleteFile(String path, {String message = ''}) =>
      inner.deleteFile(path);

  @override
  Future<bool> canAccessRemote() => inner.canAccessRemote();

  @override
  void close() => inner.close();
}
