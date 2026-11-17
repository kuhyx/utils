/// Seals writes and opens reads of one app's tree (the Dart twin of
/// `rtdb_relay/seal.py`): each unit becomes crdt_sync's [E2eCipher] blob
/// with the unit's full path as AAD, so a blob moved elsewhere does not open.
library;

import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart' show E2eCipher;
import 'package:rtdb_relay/src/layout.dart';

Object? _pruned(Object? value) {
  if (value is! Map) return value;
  final out = <String, Object?>{};
  for (final e in value.entries) {
    final v = _pruned(e.value);
    if (v != null) out[e.key as String] = v;
  }
  return out.isEmpty ? null : out;
}

/// Seals writes and opens reads under [root] with [cipher].
class RelaySealer {
  /// Creates the sealer for [layout]; [root] overrides its e2e root.
  new(this.cipher, {required this.layout, String? root})
    : root = root ?? layout.root;

  /// The tree rules.
  final RelayLayout layout;

  /// The key's cipher.
  final E2eCipher cipher;

  /// The e2e root every relative path hangs off.
  final String root;

  String _aad(List<String> parts) => [root, ...parts].join('/');

  /// [value] as it may be stored at [rel]; throws [E2eLayoutError] for an
  /// unknown path.
  Future<Object?> seal(String rel, Object? value) =>
      _seal(e2eParts(rel), value);

  /// A PATCH body for [rel]: each (multi-segment) key sealed on its own.
  Future<Map<String, Object?>> sealPatch(
    String rel,
    Map<String, Object?> body,
  ) async {
    final base = e2eParts(rel);
    final kind = layout.classify(base).kind;
    if (kind == E2eRuleKind.unit || kind == E2eRuleKind.below) {
      throw E2eLayoutError('PATCH into sealed unit $rel');
    }
    return {
      for (final e in body.entries)
        e.key: await _seal([...base, ...e2eParts(e.key)], e.value),
    };
  }

  Future<Object?> _seal(List<String> parts, Object? value) async {
    final rule = layout.classify(parts);
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

  /// [value] read at [rel] with every unit in it opened. A unit that does
  /// not open reads as absent; legacy plaintext is returned as stored.
  Future<Object?> open(String rel, Object? value) =>
      _open(e2eParts(rel), value);

  Future<Object?> _open(List<String> parts, Object? value) async {
    final rule = layout.classify(parts);
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
