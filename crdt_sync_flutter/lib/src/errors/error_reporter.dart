/// Records errors the user saw (or that escaped) in the [ErrorQueue].
library;

import 'package:crdt_sync_flutter/src/errors/app_errors_config.dart';
import 'package:crdt_sync_flutter/src/errors/error_entry.dart';
import 'package:crdt_sync_flutter/src/errors/error_queue.dart';

/// The one door for the app-wide hooks (from kartka's `ErrorReporter`).
///
/// It guards the queue against error loops: an identical `kind` + message
/// inside [window] is dropped, and at most [maxPerMinute] reports are kept a
/// minute. It never throws and never reports from inside a report.
class ErrorReporter {
  /// A reporter into [queue] for [config]'s app, reading time from [now].
  ErrorReporter(this.queue, {required this.config, DateTime Function()? now})
    : _now = now ?? DateTime.now;

  /// How long an identical error stays suppressed.
  static const window = Duration(seconds: 30);

  /// Most reports kept in one minute.
  static const maxPerMinute = 20;

  /// Innermost frames always kept; the rest are the app's own frames.
  static const _innerFrames = 2;

  /// Where reports go.
  final ErrorQueue queue;

  /// The app reported for.
  final AppErrorsConfig config;

  /// The route on top now (an [AppErrorsRouteObserver] keeps it current).
  String? route;

  final DateTime Function() _now;
  final _lastSeen = <String, DateTime>{};
  DateTime? _minute;
  int _inMinute = 0;
  bool _busy = false;

  /// Records [error] (with [stack]) as a [kind] report, unless suppressed.
  void report(String kind, Object? error, {StackTrace? stack}) {
    if (_busy) return;
    _busy = true;
    try {
      final at = _now().toUtc();
      final text = '${error ?? 'unknown error'}';
      if (_allowed('$kind|$text', at)) {
        queue.add(
          ErrorEntry(
            at: at,
            kind: kind,
            error: text,
            stack: _focus(stack),
            route: route,
          ),
        );
      }
    } on Object {
      // An error whose toString throws: nothing sensible to record.
    } finally {
      _busy = false;
    }
  }

  bool _allowed(String key, DateTime at) {
    _lastSeen.removeWhere((_, seen) => at.difference(seen) >= window);
    if (_lastSeen.containsKey(key)) return false;
    final minute = _minute;
    if (minute == null || at.difference(minute) >= const Duration(minutes: 1)) {
      _minute = at;
      _inMinute = 0;
    }
    if (_inMinute >= maxPerMinute) return false;
    _inMinute++;
    _lastSeen[key] = at;
    return true;
  }

  /// The innermost frames, then the app's own frames, so a framework-deep
  /// stack still names the app code that triggered it.
  List<String> _focus(StackTrace? stack) {
    if (stack == null) return const [];
    final frames = [
      for (final line in '$stack'.split('\n'))
        if (line.trim().isNotEmpty) line.trim(),
    ];
    return [
      ...frames.take(_innerFrames),
      ...frames.skip(_innerFrames).where((f) => f.contains(config.mark)),
    ];
  }
}
