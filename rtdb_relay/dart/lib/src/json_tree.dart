/// Applies RTDB stream events to a local copy of the listened subtree.
///
/// Pure and copy-on-write: callers keep the previous tree, so a listener can
/// diff old against new without the tree changing under it.
library;

import 'package:rtdb_relay/src/rtdb_event.dart';

List<String> _segments(String path) =>
    path.split('/').where((s) => s.isNotEmpty).toList();

/// Returns [root] with [value] set at [path] (`/` replaces the root).
/// A null [value] deletes; maps left empty collapse to null, as in RTDB.
Object? setAt(Object? root, String path, Object? value) =>
    _set(root, _segments(path), value);

Object? _set(Object? node, List<String> segs, Object? value) {
  if (segs.isEmpty) return value;
  final map = node is Map<String, dynamic>
      ? Map<String, dynamic>.of(node)
      : <String, dynamic>{};
  final child = _set(map[segs.first], segs.sublist(1), value);
  if (child == null) {
    map.remove(segs.first);
  } else {
    map[segs.first] = child;
  }
  return map.isEmpty ? null : map;
}

/// Reads the value at [path] in [root]; null when absent.
Object? getAt(Object? root, String path) {
  var node = root;
  for (final seg in _segments(path)) {
    if (node is! Map<String, dynamic>) return null;
    node = node[seg];
  }
  return node;
}

/// Applies one stream event; non-data events return [root] unchanged.
Object? applyEvent(Object? root, RtdbEvent event) {
  switch (event) {
    case RtdbPut(:final path, :final data):
      return setAt(root, path, data);
    case RtdbPatch(:final path, :final data):
      var next = root;
      for (final entry in data.entries) {
        next = setAt(next, '$path/${entry.key}', entry.value);
      }
      return next;
    case RtdbConnected():
    case RtdbDisconnected():
    case RtdbKeepAlive():
    case RtdbCancel():
    case RtdbAuthRevoked():
      return root;
  }
}
