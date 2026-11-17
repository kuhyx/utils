/// Reports user-visible waits over a second (from kartka's `slow_wait.dart`).
library;

import 'dart:async';

import 'package:crdt_sync_flutter/src/errors/error_entry.dart';
import 'package:crdt_sync_flutter/src/errors/error_queue.dart';

/// Writes every wait that outlasts [threshold] as one `perf.slow` report
/// (route when it began, operation, milliseconds).
///
/// A wait that ends within [threshold] writes nothing. One still going after
/// [stillWaiting] is written at once (a hung load never ends), and its end
/// writes a second report with the same wait id. The PC groups by route +
/// operation only, so every slow wait of one operation is one ticket. At most
/// [maxPerMinute] reports a minute. Never throws.
class SlowWaitReporter {
  /// A reporter into [queue]; [route] reads the route on top.
  SlowWaitReporter(
    this.queue, {
    DateTime Function()? now,
    String? Function()? route,
    this.threshold = const Duration(seconds: 1),
    this.stillWaiting = const Duration(seconds: 5),
  }) : _now = now ?? DateTime.now,
       _route = route ?? _noRoute;

  static String? _noRoute() => null;

  /// Most reports kept in one minute.
  static const maxPerMinute = 30;

  /// Where reports go.
  final ErrorQueue queue;

  /// A wait must last longer than this to be reported.
  final Duration threshold;

  /// A wait this long is reported before it ends.
  final Duration stillWaiting;

  final DateTime Function() _now;
  final String? Function() _route;
  DateTime? _minute;
  int _inMinute = 0;
  int _serial = 0;

  /// Starts timing a wait on [operation] (`list.load`); call
  /// [SlowWait.end] when it is over.
  SlowWait begin(String operation) {
    final at = _now();
    return SlowWait._(
      this,
      operation: operation,
      route: _route(),
      started: at,
      id: '${at.microsecondsSinceEpoch.toRadixString(36)}-${_serial++}',
    );
  }

  void _write(SlowWait w, Duration took, {required bool still}) {
    final at = _now().toUtc();
    final minute = _minute;
    if (minute == null || at.difference(minute) >= const Duration(minutes: 1)) {
      _minute = at;
      _inMinute = 0;
    }
    if (_inMinute >= maxPerMinute) return;
    _inMinute++;
    final ms = took.inMilliseconds;
    queue.add(
      ErrorEntry(
        at: at,
        kind: perfSlowKind,
        error: '${w.operation} waited $ms ms',
        route: w.route,
        operation: w.operation,
        durationMs: ms,
        waitId: w.id,
        still: still,
      ),
    );
  }
}

/// One timed wait of a [SlowWaitReporter].
class SlowWait {
  SlowWait._(
    this._reporter, {
    required this.operation,
    required this.route,
    required this.started,
    required this.id,
  }) {
    _timer = Timer(_reporter.stillWaiting, _stillGoing);
  }

  final SlowWaitReporter _reporter;

  /// What is awaited.
  final String operation;

  /// The route on top when the wait began.
  final String? route;

  /// When it began.
  final DateTime started;

  /// Names this wait across its reports.
  final String id;

  late final Timer _timer;
  bool _reportedStill = false;
  bool _ended = false;

  void _stillGoing() {
    _reportedStill = true;
    _reporter._write(this, _reporter._now().difference(started), still: true);
  }

  /// Ends the wait; writes it when it lasted over the threshold. Repeat
  /// calls do nothing.
  void end() {
    if (_ended) return;
    _ended = true;
    _timer.cancel();
    final took = _reporter._now().difference(started);
    if (_reportedStill || took > _reporter.threshold) {
      _reporter._write(this, took, still: false);
    }
  }
}
