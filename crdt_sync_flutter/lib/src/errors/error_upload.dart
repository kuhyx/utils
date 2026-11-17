/// Uploads queued reports to RTDB `/<app>/errors/<device>/<id>`, where the
/// PC's `app-errors` ingest collects them (from kartka's `error_upload.dart`).
library;

import 'dart:async';
import 'dart:math' as math;

import 'package:crdt_sync_flutter/src/errors/app_errors_config.dart';
import 'package:crdt_sync_flutter/src/errors/error_entry.dart';
import 'package:crdt_sync_flutter/src/errors/error_queue.dart';
import 'package:crdt_sync_flutter/src/errors/report_redact.dart';

/// Characters an RTDB key cannot hold.
final _unsafeKey = RegExp(r'[.#$\[\]/]');

/// A multi-path RTDB update of `path` (`FirebaseRestClient.patchValues`).
typedef ErrorSink =
    Future<void> Function(String path, Map<String, Object?> values);

/// Pushes the [ErrorQueue] to RTDB and drops what was sent.
///
/// Writes go straight to the RTDB client, never through the sync engine, so
/// they bump no `revs/` and no peer fetches them. A retried push is
/// idempotent (the id is a hash of the entry). Best-effort: debounced after
/// appends, backing off on failure, never throws.
class ErrorUploader {
  /// An uploader of [queue] for [config]'s app; [sink] is null while signed
  /// out.
  ErrorUploader(
    this.queue, {
    required this.config,
    required this.sink,
    required this.deviceId,
    this.debounce = const Duration(seconds: 5),
  });

  /// Entries per RTDB write.
  static const batch = 50;

  /// First retry delay after a failed push; doubles up to [maxBackoff].
  static const minBackoff = Duration(seconds: 30);

  /// Longest retry delay.
  static const maxBackoff = Duration(minutes: 15);

  /// The reports waiting.
  final ErrorQueue queue;

  /// The app's identity, stamped on every upload.
  final AppErrorsConfig config;

  /// The RTDB writer, or null while signed out.
  final Future<ErrorSink?> Function() sink;

  /// This install's device id.
  final Future<String> Function() deviceId;

  /// Quiet time after an append before a flush.
  final Duration debounce;

  StreamSubscription<ErrorEntry>? _sub;
  Timer? _timer;
  Duration _backoff = minBackoff;
  Future<bool> _tail = Future.value(true);

  /// Flushes [debounce] after each append.
  void start() => _sub ??= queue.added.listen((_) => schedule());

  /// Flushes after [delay] (default [debounce]), replacing a pending one.
  void schedule([Duration? delay]) {
    _timer?.cancel();
    _timer = Timer(delay ?? debounce, () => unawaited(flush()));
  }

  /// Stops listening and cancels a pending flush.
  void dispose() {
    unawaited(_sub?.cancel());
    _sub = null;
    _timer?.cancel();
  }

  /// Pushes what is queued; true when nothing is left. Flushes run one at a
  /// time; a failure schedules a retry with backoff.
  Future<bool> flush() => _tail = _tail.then((_) => _flushOnce());

  Future<bool> _flushOnce() async {
    final pending = queue.entries;
    if (pending.isEmpty) return true;
    try {
      final write = await sink();
      if (write == null) throw StateError('signed out');
      final device = (await deviceId()).replaceAll(_unsafeKey, '_');
      for (var i = 0; i < pending.length; i += batch) {
        final chunk = pending.sublist(i, math.min(i + batch, pending.length));
        await write('${config.app}/errors', {
          for (final e in chunk) '$device/${ErrorQueue.idOf(e)}': _payload(e),
        });
        queue.remove({for (final e in chunk) ErrorQueue.idOf(e)});
      }
      _backoff = minBackoff;
      return true;
    } on Object {
      schedule(_backoff);
      _backoff = _backoff * 2 > maxBackoff ? maxBackoff : _backoff * 2;
      return false;
    }
  }

  Map<String, Object?> _payload(ErrorEntry e) => {
    for (final MapEntry(:key, :value) in e.toJson().entries)
      key: switch (value) {
        final String s => redactForReport(s),
        final List<Object?> l => [for (final f in l) redactForReport('$f')],
        _ => value,
      },
    'repo': config.repo,
    'mark': config.mark,
    'build': config.build,
    'version': ?config.version,
  };
}
