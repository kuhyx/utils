/// Every request in flight, followed over ONE listen (tutor DOCS-contract
/// §4, §9).
///
/// RTDB speaks HTTP/1.1, so a browser holds at most 6 connections to it and
/// every listen keeps one for good. A listen per request let a Home request
/// still running under a Session turn take the app to 6 and starve the next
/// write. One `requests` listen ranged from the oldest followed rid
/// (`orderBy="$key"&startAt`: ULIDs sort by time) serves them all; another
/// device's request in that window rides along, unread.
///
/// `inFlight` counts the requests followed; the shared `rev` listen yields
/// to it (`rev_watcher.dart`), so requests and `rev` share one connection.
/// A request's PUT goes out before its follow starts, while `rev` may still
/// be open: 4 streams and the PUT, 1 connection to spare.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:rtdb_relay/src/json_tree.dart';
import 'package:rtdb_relay/src/rtdb_client.dart' show keyRangeQuery;
import 'package:rtdb_relay/src/rtdb_event.dart';
import 'package:rtdb_relay/src/rtdb_stream.dart';

/// The shared `requests` listen.
class RequestHub {
  /// Creates the hub over [_stream], following the requests node at
  /// [requestsPath] (`<root>/requests`).
  new(this._stream, this.requestsPath);

  final RtdbStream _stream;

  /// The full path of the requests node.
  final String requestsPath;

  /// Requests being followed; while above 0, `rev` waits.
  final ValueNotifier<int> inFlight = ValueNotifier(0);

  final Map<String, List<StreamController<Object?>>> _watchers = {};
  // Cancelled in _close(); the lint cannot see across methods.
  // ignore: cancel_subscriptions
  StreamSubscription<RtdbEvent>? _sub;
  String? _from;
  Object? _tree;

  /// The `requests/{rid}` node each time it changes (null while absent),
  /// until the subscription is cancelled.
  Stream<Object?> watch(String rid) {
    late final StreamController<Object?> out;
    out = StreamController<Object?>(
      // `rev` lets go before this listen opens and comes back only after
      // it closed, so the two never hold two connections at once.
      onListen: () {
        inFlight.value++;
        _watchers.putIfAbsent(rid, () => []).add(out);
        _cover(rid);
      },
      onCancel: () {
        final list = _watchers[rid]!..remove(out);
        if (list.isEmpty) _watchers.remove(rid);
        if (_watchers.isEmpty) _close();
        inFlight.value--;
      },
    );
    return out.stream;
  }

  /// Makes the listen reach back to [rid]: reopened from it when it is
  /// older than the range's start, else [rid]'s node so far is handed over.
  void _cover(String rid) {
    final from = _from;
    if (from != null && from.compareTo(rid) <= 0) {
      final node = getAt(_tree, rid);
      if (node != null) _send(rid, node);
      return;
    }
    _close();
    _from = rid;
    _sub = _stream
        .listen(requestsPath, query: keyRangeQuery(rid))
        .listen(_on, onDone: _ended);
  }

  // The transport gave up for good (rules `cancel`): every follow ends with
  // no result, as its own listen's end did.
  void _ended() {
    _sub = null;
    _from = null;
    _tree = null;
    for (final list in [..._watchers.values]) {
      for (final out in [...list]) {
        unawaited(out.close());
      }
    }
  }

  void _close() {
    final sub = _sub;
    _sub = null;
    _from = null;
    _tree = null;
    unawaited(sub?.cancel());
  }

  void _on(RtdbEvent event) {
    if (event is! RtdbPut && event is! RtdbPatch) return;
    final before = _tree;
    _tree = applyEvent(before, event);
    // Copy-on-write: a node no event touched is the very same object.
    final snapshot = event is RtdbPut && event.path == '/';
    for (final rid in [..._watchers.keys]) {
      final node = getAt(_tree, rid);
      // A snapshot (each connect) answers every watcher, as a per-request
      // listen did: absent means queued.
      if (snapshot || !identical(node, getAt(before, rid))) _send(rid, node);
    }
  }

  void _send(String rid, Object? node) {
    for (final out in [...?_watchers[rid]]) {
      out.add(node);
    }
  }
}
