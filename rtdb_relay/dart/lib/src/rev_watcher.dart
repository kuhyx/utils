/// "Did X change?" from a `rev` node of counters (the tutor's
/// DOCS-contract §3, §9: `rev.catalog`, `rev.stats`).
///
/// One shared listen for every screen: each `changesOf(key)` is a broadcast
/// stream; the first listener of any opens the SSE and the last cancel
/// closes it. The listen also pauses while the app is hidden and resumes
/// when it is back in front.
///
/// While a request is in flight ([RevWatcher.new]'s `yieldTo` above 0) the
/// listen stays closed: RTDB speaks HTTP/1.1, every listen holds one of the
/// browser's 6 connections, and the request's own listen takes this one.
/// Nothing is lost: the snapshot on reopening emits any move made meanwhile.
///
/// Only real moves are emitted; the full snapshot every (re)connect resends
/// while a value is unchanged is not a move. A snapshot whose value *did*
/// change (the worker moved it while the app was hidden) is.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:rtdb_relay/src/json_tree.dart';
import 'package:rtdb_relay/src/rtdb_event.dart';
import 'package:rtdb_relay/src/rtdb_stream.dart';

/// Counter [key] of a `rev` tree; 0 when absent.
int revOf(Object? rev, String key) {
  final value = rev is Map<String, dynamic> ? rev[key] : null;
  return value is num ? value.toInt() : 0;
}

/// Whether the app counts as in front for [state] (null: not reported yet).
/// `inactive` keeps whatever was decided before: desktop web reports it on
/// a mere focus change, which is no reason to drop or reopen the listen.
bool? foregroundFor(AppLifecycleState? state) => switch (state) {
  null || AppLifecycleState.resumed => true,
  AppLifecycleState.inactive => null,
  AppLifecycleState.hidden ||
  AppLifecycleState.paused ||
  AppLifecycleState.detached => false,
};

/// Streams `rev` while someone listens and the app is in front.
class RevWatcher {
  /// Creates the watcher; `binding` (tests) reports the app lifecycle;
  /// while [yieldTo] is above 0 the listen is closed.
  /// [path] is the full path of the `rev` node.
  new(this._stream, this.path, {this._binding, this.yieldTo}) {
    yieldTo?.addListener(_yield);
  }

  final RtdbStream _stream;
  final WidgetsBinding? _binding;

  /// The full path of the `rev` node.
  final String path;

  /// Requests in flight (`RequestRelay.inFlight`).
  final ValueListenable<int>? yieldTo;

  bool get _yielding => (yieldTo?.value ?? 0) > 0;

  final Map<String, StreamController<int>> _outs = {};
  final Map<String, int> _last = {};

  // Cancelled in _disconnect(); the lint cannot see across methods.
  // ignore: cancel_subscriptions
  StreamSubscription<RtdbEvent>? _sub;
  AppLifecycleListener? _lifecycle;
  bool _foreground = true;
  Object? _tree;

  /// The new `rev.<key>` each time it moves.
  Stream<int> changesOf(String key) => _outs.putIfAbsent(key, () {
    // A counter absent so far reads 0: its baseline once any event came.
    if (_tree != null) _last.putIfAbsent(key, () => revOf(_tree, key));
    return StreamController.broadcast(onListen: _open, onCancel: _release);
  }).stream;

  bool get _wanted => _outs.values.any((c) => c.hasListener);

  /// Whether the SSE listen is open (tests).
  bool get listening => _sub != null;

  /// Tells the watcher the app went to the back (false) or front (true).
  void foreground({required bool visible}) {
    _foreground = visible;
    visible ? _connect() : unawaited(_disconnect());
  }

  /// Closes the listen and the stream.
  Future<void> dispose() async {
    yieldTo?.removeListener(_yield);
    for (final out in _outs.values) {
      await out.close();
    }
    await _close();
  }

  // The first listener of either stream opens the listen, the last closes it.
  void _open() {
    if (_lifecycle != null) return;
    final binding = _binding ?? WidgetsBinding.instance;
    _foreground = foregroundFor(binding.lifecycleState) ?? true;
    _lifecycle = AppLifecycleListener(
      binding: binding,
      onStateChange: (state) {
        final visible = foregroundFor(state);
        if (visible != null) foreground(visible: visible);
      },
    );
    _connect();
  }

  Future<void> _release() async {
    if (!_wanted) await _close();
  }

  Future<void> _close() async {
    _lifecycle?.dispose();
    _lifecycle = null;
    await _disconnect();
  }

  void _yield() => _yielding ? unawaited(_disconnect()) : _connect();

  void _connect() {
    if (_sub != null || !_foreground || !_wanted || _yielding) return;
    _tree = null;
    _sub = _stream.listen(path).listen(_on, onDone: () => _sub = null);
  }

  Future<void> _disconnect() async {
    final sub = _sub;
    _sub = null;
    await sub?.cancel();
  }

  void _on(RtdbEvent event) {
    if (event is RtdbConnected) _tree = null;
    if (event is! RtdbPut && event is! RtdbPatch) return;
    final tree = _tree = applyEvent(_tree, event);
    // Every counter keeps a baseline, watched or not, so a stream opened
    // later still sees only real moves.
    final keys = {
      if (tree is Map<String, dynamic>) ...tree.keys,
      ..._outs.keys,
    };
    for (final key in keys) {
      final now = revOf(tree, key);
      final before = _last[key];
      _last[key] = now;
      // The first value ever is the baseline the screens loaded against.
      final out = _outs[key];
      if (before != null && before != now && out != null && !out.isClosed) {
        out.add(now);
      }
    }
  }
}
