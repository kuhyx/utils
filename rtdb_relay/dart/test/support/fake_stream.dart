/// An [RtdbStream] whose events the test pushes by path.
///
/// It also counts the listens open at once, as a browser counts the
/// connections they hold: RTDB speaks HTTP/1.1 and Chrome gives a host 6, so
/// the app must keep its streams well under that (`stream_budget_test`).
library;

import 'dart:async';
import 'dart:math';

import 'package:rtdb_relay/src/rtdb_client.dart';
import 'package:rtdb_relay/src/rtdb_event.dart';
import 'package:rtdb_relay/src/rtdb_stream.dart';

/// The fake transport.
class FakeStream implements RtdbStream {
  /// Listens by path (the latest one per path), open or not.
  final Map<String, StreamController<RtdbEvent>> listens = {};

  /// The query of the latest listen per path.
  final Map<String, Map<String, String>> queries = {};

  final Set<StreamController<RtdbEvent>> _open = {};
  final Map<StreamController<RtdbEvent>, String> _paths = {};

  /// The most listens ever open at once, and which they were.
  int peak = 0;

  /// The paths open when [peak] was reached.
  List<String> peakPaths = const [];

  /// The paths of the listens open now.
  List<String> get openPaths => [for (final c in _open) _paths[c]!];

  @override
  RtdbClient get client => throw UnimplementedError();

  @override
  Stream<RtdbEvent> listen(
    String path, {
    Map<String, String> query = const {},
  }) {
    queries[path] = query;
    late final StreamController<RtdbEvent> c;
    c = StreamController<RtdbEvent>(
      onListen: () {
        _open.add(c);
        if (_open.length > peak) {
          peak = _open.length;
          peakPaths = openPaths;
        }
      },
      onCancel: () => _open.remove(c),
    );
    _paths[c] = path;
    return (listens[path] = c).stream;
  }

  /// Delivers [event] for [path] as RTDB does: to the open listen on that
  /// path, else to the nearest open listen above it with the event's path
  /// prefixed by the rest. False when nothing listens there.
  bool emit(String path, RtdbEvent event) {
    for (var at = path; at.isNotEmpty; at = _parent(at)) {
      final c = listens[at];
      if (c == null || !_open.contains(c)) continue;
      final rest = path.substring(at.length);
      c.add(rest.isEmpty ? event : _under(rest, event));
      return true;
    }
    return false;
  }

  static String _parent(String path) =>
      path.substring(0, max(0, path.lastIndexOf('/')));

  static RtdbEvent _under(String rest, RtdbEvent event) {
    String join(String p) => p == '/' ? rest : '$rest$p';
    return switch (event) {
      RtdbPut(:final path, :final data) => RtdbPut(join(path), data),
      RtdbPatch(:final path, :final data) => RtdbPatch(join(path), data),
      _ => event,
    };
  }
}
