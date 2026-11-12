/// The per-record wire envelope: record ids, the tombstone and the newest HLC
/// stay in clear so the relay can order and inspect; every field name and
/// value is sealed. Merge still runs on the decrypted [Log].
library;

import 'dart:convert';

import 'e2e_cipher.dart';
import 'hlc.dart';

const int _envelopeVersion = 1;

/// Whether [text] is an envelope (explicit `"v"` integer), not legacy plaintext.
///
/// A legacy log maps record ids to objects, so an id named `v` still maps to
/// a map, never an int.
bool isE2eEnvelope(String text) {
  try {
    final json = jsonDecode(text);
    return json is Map && json['v'] is int;
  } on FormatException {
    return false;
  }
}

String _aad(
  String path,
  String id,
  bool deleted,
  String? deletedHlc,
  String? h,
) => '$path#$id#${deleted ? 1 : 0}#${deletedHlc ?? ''}#${h ?? ''}';

/// Seals a log (the `logToJson` shape) into an envelope. Text that is not
/// log-shaped is sealed whole, so nothing is ever pushed in clear.
Future<String> sealLogText(
  String text,
  E2eCipher cipher, {
  required String path,
}) async {
  final Map<String, dynamic> raw;
  try {
    raw = (jsonDecode(text) as Map).cast<String, dynamic>();
    for (final entry in raw.entries) {
      final rec = entry.value as Map;
      if (rec['id'] != entry.key || rec['fields'] is! Map) {
        throw const FormatException('not a log');
      }
    }
  } on Object {
    return jsonEncode({
      'v': _envelopeVersion,
      'b': await cipher.seal(text, path: path),
    });
  }
  final records = <String, Object?>{};
  for (final entry in raw.entries) {
    final rec = (entry.value as Map).cast<String, dynamic>();
    final fields = (rec['fields'] as Map).cast<String, dynamic>();
    Hlc? newest;
    for (final field in fields.values) {
      final hlc = Hlc.fromStr((field as List)[1] as String);
      if (newest == null || hlc > newest) newest = hlc;
    }
    final deleted = rec['deleted'] as bool? ?? false;
    final deletedHlc = rec['deleted_hlc'] as String?;
    final h = newest?.toStr();
    records[entry.key] = {
      'd': deleted,
      'dh': deletedHlc,
      'h': h,
      'p': await cipher.seal(
        jsonEncode(fields),
        path: _aad(path, entry.key, deleted, deletedHlc, h),
      ),
    };
  }
  return jsonEncode({'v': _envelopeVersion, 'r': records});
}

/// Opens an envelope back to the `logToJson` shape. Legacy plaintext is
/// returned as-is while the cipher accepts it.
Future<String> openLogText(
  String text,
  E2eCipher cipher, {
  required String path,
}) async {
  if (!isE2eEnvelope(text)) {
    if (cipher.acceptPlaintext) return text;
    throw E2eDecryptError('plaintext blob at $path after migration');
  }
  final json = (jsonDecode(text) as Map).cast<String, dynamic>();
  if (json['v'] != _envelopeVersion) {
    throw E2eDecryptError(
      'blob at $path uses format ${json['v']}; update the app to read it',
    );
  }
  final whole = json['b'];
  if (whole is String) return cipher.open(whole, path: path);
  final records = json['r'];
  if (records is! Map) throw E2eDecryptError('envelope at $path is mis-shaped');
  final out = <String, Object?>{};
  for (final entry in records.entries) {
    final id = entry.key as String;
    final rec = entry.value;
    if (rec is! Map || rec['p'] is! String || rec['d'] is! bool) {
      throw E2eDecryptError('record $id at $path is mis-shaped');
    }
    final deletedHlc = rec['dh'] as String?;
    final h = rec['h'] as String?;
    final clear = await cipher.open(
      rec['p'] as String,
      path: _aad(path, id, rec['d'] as bool, deletedHlc, h),
    );
    out[id] = {
      'id': id,
      'fields': jsonDecode(clear),
      'deleted': rec['d'],
      'deleted_hlc': deletedHlc,
    };
  }
  return jsonEncode(out);
}
