/// Which RTDB nodes are sealed, and how (the Dart twin of
/// `rtdb_relay/layout.py`).
///
/// Keys stay clear; every *unit* (a node one writer writes whole) is stored
/// as `{"_e2e": <blob>, <clear siblings>}`. A `clear` pattern covers its whole
/// subtree; a unit pattern maps to the fields it keeps clear (server
/// timestamps). `*` matches one segment. A write the layout has no rule for
/// throws: nothing new leaks by accident.
library;

import 'package:crdt_sync/crdt_sync.dart' show E2eLayout;

/// The key a sealed unit keeps its blob under.
const String kSealedKey = '_e2e';

/// The rules every relay app needs: request leases are clear, requests,
/// results and worker presence are sealed units.
const List<String> kRelayClear = ['requests/*/claim'];

/// The relay's own units and the fields each keeps clear.
const Map<String, Set<String>> kRelayUnits = {
  'presence/workers/*': {'beat'},
  'requests/*/req': {'created'},
  'requests/*/result': {'at'},
};

/// A write the layout refuses (unknown path, or inside a sealed unit).
class E2eLayoutError implements Exception {
  /// Creates the error.
  const new(this.message);

  /// What was refused.
  final String message;

  @override
  String toString() => 'E2eLayoutError: $message';
}

/// Where a node falls in the layout.
enum E2eRuleKind {
  /// Stored as is (ids, counters, lease times).
  clear,

  /// Sealed whole.
  unit,

  /// Inside a unit: never written on its own.
  below,

  /// A map of clear keys above units.
  struct,

  /// No rule: refused on write.
  unknown,
}

/// The rule for one node.
class E2eRule {
  /// Creates the rule.
  const new(this.kind, [this.depth = 0, this.keep = const {}]);

  /// Its kind.
  final E2eRuleKind kind;

  /// For [E2eRuleKind.below]: how many segments the unit has.
  final int depth;

  /// For a unit: the fields kept clear.
  final Set<String> keep;
}

/// [path]'s segments, empty ones dropped.
List<String> e2eParts(String path) =>
    path.split('/').where((s) => s.isNotEmpty).toList();

bool _matches(List<String> pattern, List<String> parts) {
  if (pattern.length != parts.length) return false;
  for (var i = 0; i < parts.length; i++) {
    if (pattern[i] != '*' && pattern[i] != parts[i]) return false;
  }
  return true;
}

/// One app's sealed tree: its root and its rules.
class RelayLayout {
  /// The layout for app root [base] (e.g. `tutor/v1`); the sealed tree lives
  /// at crdt_sync's e2e prefix of it (`tutor/v1-e2e`). Pattern order matters:
  /// the first matching rule wins, clear before units.
  new(this.base, {required this.clear, required this.units})
    : root = E2eLayout.of(base).prefix;

  /// The pre-e2e root; the key header hangs off it (crdt_sync).
  final String base;

  /// The e2e root every relative path hangs off.
  final String root;

  /// Clear subtrees.
  final List<String> clear;

  /// Sealed units and the fields each keeps clear.
  final Map<String, Set<String>> units;

  /// The rule for the node at [parts] (relative to [root]).
  E2eRule classify(List<String> parts) {
    for (final pattern in clear) {
      final pat = pattern.split('/');
      if (pat.length <= parts.length &&
          _matches(pat, parts.sublist(0, pat.length))) {
        return const E2eRule(E2eRuleKind.clear);
      }
    }
    for (final entry in units.entries) {
      final pat = entry.key.split('/');
      if (_matches(pat, parts)) {
        return E2eRule(E2eRuleKind.unit, pat.length, entry.value);
      }
      if (pat.length < parts.length &&
          _matches(pat, parts.sublist(0, pat.length))) {
        return E2eRule(E2eRuleKind.below, pat.length, entry.value);
      }
    }
    for (final pattern in [...clear, ...units.keys]) {
      final pat = pattern.split('/');
      if (parts.length < pat.length &&
          _matches(pat.sublist(0, parts.length), parts)) {
        return const E2eRule(E2eRuleKind.struct);
      }
    }
    return const E2eRule(E2eRuleKind.unknown);
  }

  /// The sealed unit [rel] lies strictly below, or null.
  String? unitPath(String rel) {
    final parts = e2eParts(rel);
    final rule = classify(parts);
    return rule.kind == E2eRuleKind.below
        ? parts.sublist(0, rule.depth).join('/')
        : null;
  }

  /// [path] relative to [root], or null when outside it.
  String? rel(String path) {
    final clean = e2eParts(path).join('/');
    if (clean == root) return '';
    return clean.startsWith('$root/') ? clean.substring(root.length + 1) : null;
  }
}
