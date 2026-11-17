// FROZEN copy of the tutor app's lib/sync/e2e_seal.dart at tutor d72bba7, the
// code the phone APK ran before the extraction. Only the differential test
// reads it; never edit it (doc comments stripped for the line cap).
// ignore_for_file: type=lint
/// End-to-end encryption of the tutor's RTDB tree (DOCS-contract §12).
library;

import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart' show E2eCipher, E2eLayout;

const String kOldRoot = 'tutor/v1';

final E2eLayout kE2eLayout = E2eLayout.of(kOldRoot);

const String kSealedKey = '_e2e';

const List<String> _clear = [
  'meta',
  'rev',
  'migration',
  'requests/*/claim',
  'sessions/*/progress/rid',
];

const Map<String, Set<String>> _units = {
  'live': {},
  'prefs/*': {},
  'stats/*': {},
  'presence/workers/*': {'beat'},
  'presence/clients/*': {'seen'},
  'uploads/*/*': {},
  'requests/*/req': {'created'},
  'requests/*/result': {'at'},
  'sessions/*/meta/*': {},
  'sessions/*/msgs/*': {},
  'sessions/*/receipts/*': {},
  'sessions/*/user/*': {},
  'sessions/*/progress/steps/*': {},
  'session_index/*': {},
  'subjects/*/meta': {},
  'subjects/*/plan': {},
  'subjects/*/cards': {},
  'subjects/*/concepts': {},
  'log/*/*': {},
  'feedback/*': {},
};

class E2eLayoutError implements Exception {
  const new(this.message);

  final String message;

  @override
  String toString() => 'E2eLayoutError: $message';
}

enum E2eRuleKind { clear, unit, below, struct, unknown }

class E2eRule {
  const new(this.kind, [this.depth = 0, this.keep = const {}]);

  final E2eRuleKind kind;

  final int depth;

  final Set<String> keep;
}

Object? _pruned(Object? value) {
  if (value is! Map) return value;
  final out = <String, Object?>{};
  for (final e in value.entries) {
    final v = _pruned(e.value);
    if (v != null) out[e.key as String] = v;
  }
  return out.isEmpty ? null : out;
}

List<String> e2eParts(String path) =>
    path.split('/').where((s) => s.isNotEmpty).toList();

bool _matches(List<String> pattern, List<String> parts) {
  if (pattern.length != parts.length) return false;
  for (var i = 0; i < parts.length; i++) {
    if (pattern[i] != '*' && pattern[i] != parts[i]) return false;
  }
  return true;
}

E2eRule classifyE2e(List<String> parts) {
  for (final pattern in _clear) {
    final pat = pattern.split('/');
    if (pat.length <= parts.length &&
        _matches(pat, parts.sublist(0, pat.length))) {
      return const E2eRule(E2eRuleKind.clear);
    }
  }
  for (final entry in _units.entries) {
    final pat = entry.key.split('/');
    if (_matches(pat, parts)) {
      return E2eRule(E2eRuleKind.unit, pat.length, entry.value);
    }
    if (pat.length < parts.length &&
        _matches(pat, parts.sublist(0, pat.length))) {
      return E2eRule(E2eRuleKind.below, pat.length, entry.value);
    }
  }
  for (final pattern in [..._clear, ..._units.keys]) {
    final pat = pattern.split('/');
    if (parts.length < pat.length &&
        _matches(pat.sublist(0, parts.length), parts)) {
      return const E2eRule(E2eRuleKind.struct);
    }
  }
  return const E2eRule(E2eRuleKind.unknown);
}

String? e2eUnitPath(String rel) {
  final parts = e2eParts(rel);
  final rule = classifyE2e(parts);
  return rule.kind == E2eRuleKind.below
      ? parts.sublist(0, rule.depth).join('/')
      : null;
}

class TutorSealer {
  new(this.cipher, {String? root}) : root = root ?? kE2eLayout.prefix;

  final E2eCipher cipher;

  final String root;

  String _aad(List<String> parts) => [root, ...parts].join('/');

  Future<Object?> seal(String rel, Object? value) =>
      _seal(e2eParts(rel), value);

  Future<Map<String, Object?>> sealPatch(
    String rel,
    Map<String, Object?> body,
  ) async {
    final base = e2eParts(rel);
    final kind = classifyE2e(base).kind;
    if (kind == E2eRuleKind.unit || kind == E2eRuleKind.below) {
      throw E2eLayoutError('PATCH into sealed unit $rel');
    }
    return {
      for (final e in body.entries)
        e.key: await _seal([...base, ...e2eParts(e.key)], e.value),
    };
  }

  Future<Object?> _seal(List<String> parts, Object? value) async {
    final rule = classifyE2e(parts);
    if (rule.kind == E2eRuleKind.clear || value == null) return value;
    if (rule.kind == E2eRuleKind.unit) {
      return await _sealUnit(parts, value, rule.keep);
    }
    if (rule.kind == E2eRuleKind.struct && value is Map) {
      return {
        for (final e in value.entries)
          e.key as String: await _seal([
            ...parts,
            ...e2eParts(e.key as String),
          ], e.value),
      };
    }
    throw E2eLayoutError(
      'no e2e rule for a ${value.runtimeType} at ${parts.join('/')} '
      '(${rule.kind.name})',
    );
  }

  Future<Map<String, Object?>?> _sealUnit(
    List<String> parts,
    Object raw,
    Set<String> keep,
  ) async {
    // As RTDB would keep it: no null members, no empty objects.
    final value = _pruned(raw);
    if (value == null) return null;
    var body = value;
    final clear = <String, Object?>{};
    if (value is Map && keep.isNotEmpty) {
      body = {
        for (final e in value.entries)
          if (!keep.contains(e.key)) e.key as String: e.value,
      };
      for (final e in value.entries) {
        if (keep.contains(e.key)) clear[e.key as String] = e.value;
      }
    }
    final blob = await cipher.seal(jsonEncode(body), path: _aad(parts));
    return {kSealedKey: blob, ...clear};
  }

  Future<Object?> open(String rel, Object? value) =>
      _open(e2eParts(rel), value);

  Future<Object?> _open(List<String> parts, Object? value) async {
    final rule = classifyE2e(parts);
    switch (rule.kind) {
      case E2eRuleKind.unit:
        return await _openUnit(parts, value);
      case E2eRuleKind.below:
        throw E2eLayoutError('read below sealed unit: ${parts.join('/')}');
      case E2eRuleKind.struct when value is Map:
        final out = <String, Object?>{};
        for (final e in value.entries) {
          final v = await _open([...parts, e.key as String], e.value);
          if (v != null) out[e.key as String] = v;
        }
        return out;
      case E2eRuleKind.struct when value is List:
        return [
          for (var i = 0; i < value.length; i++)
            await _open([...parts, '$i'], value[i]),
        ];
      case _:
        return value;
    }
  }

  Future<Object?> _openUnit(List<String> parts, Object? value) async {
    if (value is! Map || value[kSealedKey] is! String) return value;
    try {
      final text = await cipher.open(
        value[kSealedKey] as String,
        path: _aad(parts),
      );
      final data = jsonDecode(text);
      if (data is! Map) return data;
      return <String, Object?>{
        ...data.cast<String, Object?>(),
        for (final e in value.entries)
          if (e.key != kSealedKey) e.key as String: e.value,
      };
    } on FormatException {
      // E2eDecryptError is one: tampered, moved, or another key.
      return null;
    }
  }
}
