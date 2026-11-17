/// The on-device queue of reports not yet uploaded.
library;

import 'dart:async';
import 'dart:convert';

import 'package:crdt_sync_flutter/src/errors/error_entry.dart';
import 'package:crypto/crypto.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Reports waiting for upload, persisted in `SharedPreferences` (so web
/// builds keep them too): a crash, a lost connection or a signed-out device
/// loses nothing. Keeps the newest [maxEntries].
class ErrorQueue {
  ErrorQueue._(this._prefs, this._entries);

  /// The queue stored in [prefs]; a corrupt store opens empty.
  static Future<ErrorQueue> open(SharedPreferences prefs) async {
    final entries = <ErrorEntry>[];
    try {
      for (final raw in jsonDecode(prefs.getString(key) ?? '[]') as List) {
        final entry = ErrorEntry.tryFromJson(raw);
        if (entry != null) entries.add(entry);
      }
    } on FormatException {
      // A corrupt queue is dropped: reporting must never stop the app.
    }
    return ErrorQueue._(prefs, entries);
  }

  /// Preferences key of the queue.
  static const key = 'app_errors.queue';

  /// Most reports kept.
  static const maxEntries = 300;

  final SharedPreferences _prefs;
  final List<ErrorEntry> _entries;
  final _added = StreamController<ErrorEntry>.broadcast();
  Future<void> _tail = Future.value();

  /// The id of [entry]: a hash of its JSON, so a re-sent upload is a no-op.
  static String idOf(ErrorEntry entry) => sha1
      .convert(utf8.encode(jsonEncode(entry.toJson())))
      .toString()
      .substring(0, 20);

  /// What is queued, oldest first.
  List<ErrorEntry> get entries => List.unmodifiable(_entries);

  /// Fires after each [add].
  Stream<ErrorEntry> get added => _added.stream;

  /// Completes when every change so far is stored.
  Future<void> get saved => _tail;

  /// Queues [entry] and stores the queue.
  void add(ErrorEntry entry) {
    _entries.add(entry);
    if (_entries.length > maxEntries) {
      _entries.removeRange(0, _entries.length - maxEntries);
    }
    _save();
    _added.add(entry);
  }

  /// Drops the entries whose ids are in [ids] and stores the queue.
  void remove(Set<String> ids) {
    _entries.removeWhere((e) => ids.contains(idOf(e)));
    _save();
  }

  void _save() {
    final text = jsonEncode([for (final e in _entries) e.toJson()]);
    _tail = _tail.then((_) => _prefs.setString(key, text));
  }
}
