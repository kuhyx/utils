/// The one-time copy from a plaintext prefix to `<prefix>-e2e`.
///
/// Re-encrypting in place is rejected: an old build still writing the old
/// prefix would be broken mid-migration. Instead the old prefix stays
/// untouched until [deletePlaintextPrefix] verifies the copy.
library;

import 'dart:convert';

import 'e2e_key.dart';
import 'encrypting_store.dart';
import 'log.dart';
import 'record.dart';
import 'remote_store.dart';
import 'store.dart';
import 'sync.dart';

/// Where an app's encrypted data lives, derived from its old plaintext prefix.
class E2eLayout {
  const E2eLayout._(this.prefix, this.revsPath, this.e2ePath);

  /// `<oldPrefix>-e2e`, with revisions and header apart from the old ones so
  /// old builds neither see nor clobber them.
  ///
  /// A slashless prefix (`settings-sync`) keeps revisions and header inside
  /// its own node, as `defaultRevsPath` does, never at the database root.
  factory E2eLayout.of(String oldPrefix) {
    final prefix = '$oldPrefix-e2e';
    final cut = oldPrefix.lastIndexOf('/');
    if (cut < 0) {
      return E2eLayout._(prefix, '$prefix/revs', '$prefix/e2e');
    }
    final parent = oldPrefix.substring(0, cut);
    return E2eLayout._(prefix, '$parent/revs-e2e', defaultE2ePath(prefix));
  }

  final String prefix;
  final String revsPath;
  final String e2ePath;
}

class MigrationReport {
  const MigrationReport(this.copied, this.skipped);

  /// Blobs written (new or changed) this run.
  final int copied;

  /// Source blobs unreadable as a log, relative path.
  final List<String> skipped;
}

/// Every text blob under [root], keyed by path relative to it: flat
/// `<node>.json` leaves and nested `<device>/<file>` blobs. Real RTDB bulk
/// reads return direct string children only, so dirs are walked.
Future<Map<String, String>> _listBlobs(RemoteStore store, String root) async {
  final out = <String, String>{};
  if (store is BulkMapReader) {
    out.addAll(await (store as BulkMapReader).getStringMap(root));
  }
  final revs = defaultRevsPath(root);
  final header = defaultE2ePath(root);
  for (final name in await store.listDirectory(root)) {
    if (out.containsKey(name)) continue;
    final full = '$root/$name';
    if (full == header || full == revs) continue;
    final children = await _safeList(store, full);
    if (children.isEmpty) {
      final text = await _safeRead(store, full);
      if (text != null) out[name] = text;
      continue;
    }
    for (final child in children) {
      final text = await _safeRead(store, '$full/$child');
      if (text != null) out['$name/$child'] = text;
    }
  }
  out.removeWhere(
    (rel, _) => '$root/$rel' == header || '$root/$rel'.startsWith('$revs/'),
  );
  return out;
}

Future<List<String>> _safeList(RemoteStore store, String path) async {
  try {
    return await store.listDirectory(path);
  } on Object {
    return const [];
  }
}

Future<String?> _safeRead(RemoteStore store, String path) async {
  try {
    return await store.getFileText(path);
  } on Object {
    return null;
  }
}

EncryptingStore _dest(RemoteStore store, E2eKey key, E2eLayout layout) =>
    EncryptingStore(
      store,
      key,
      pathPrefix: layout.prefix,
      revsPath: layout.revsPath,
      e2ePath: layout.e2ePath,
    );

/// Order-independent signature of a log, to tell "same records" cheaply.
String _signature(Log log) {
  final ids = log.keys.toList()..sort();
  return jsonEncode([
    for (final id in ids)
      [
        id,
        log[id]!.deleted,
        log[id]!.deletedHlc?.toStr(),
        [
          for (final name in (log[id]!.fields.keys.toList()..sort()))
            [
              name,
              jsonEncode(log[id]!.fields[name]!.$1),
              log[id]!.fields[name]!.$2.toStr(),
            ],
        ],
      ],
  ]);
}

Log? _parse(String text) {
  try {
    return logFromJson(text);
  } on FormatException {
    return null;
  } on TypeError {
    return null;
  }
}

/// Copies every readable plaintext log under [fromPrefix] into the encrypted
/// prefix, merging into what is already there. Idempotent: an unchanged
/// destination is not rewritten. Never touches [fromPrefix].
Future<MigrationReport> copyToEncrypted({
  required RemoteStore store,
  required E2eKey key,
  required String fromPrefix,
  required E2eLayout layout,
}) async {
  final dest = _dest(store, key, layout);
  var copied = 0;
  final skipped = <String>[];
  final blobs = await _listBlobs(store, fromPrefix);
  for (final MapEntry(key: rel, value: text) in blobs.entries) {
    final source = _parse(text);
    if (source == null) {
      skipped.add(rel);
      continue;
    }
    final path = '${layout.prefix}/$rel';
    final existing = await dest.getFileText(path);
    final current = existing == null ? null : _parse(existing);
    final merged = mergeLogs(current ?? <String, Record>{}, source);
    if (current != null && _signature(merged) == _signature(current)) continue;
    await dest.putFileText(path, logToJson(merged), message: 'e2e copy');
    copied++;
  }
  return MigrationReport(copied, skipped);
}

/// True when every readable plaintext blob is contained in the encrypted copy
/// and none is unreadable.
Future<bool> verifyCopy({
  required RemoteStore store,
  required E2eKey key,
  required String fromPrefix,
  required E2eLayout layout,
}) async {
  final dest = _dest(store, key, layout);
  for (final MapEntry(key: rel, value: text) in (await _listBlobs(
    store,
    fromPrefix,
  )).entries) {
    final source = _parse(text);
    if (source == null) return false;
    final existing = await dest.getFileText('${layout.prefix}/$rel');
    final current = existing == null ? null : _parse(existing);
    if (current == null) return false;
    if (_signature(mergeLogs(current, source)) != _signature(current)) {
      return false;
    }
  }
  return true;
}

/// Deletes the plaintext prefix, only after [verifyCopy] passes. Returns
/// whether it deleted.
Future<bool> deletePlaintextPrefix({
  required RemoteStore store,
  required E2eKey key,
  required String fromPrefix,
  required E2eLayout layout,
}) async {
  if (!await verifyCopy(
    store: store,
    key: key,
    fromPrefix: fromPrefix,
    layout: layout,
  )) {
    return false;
  }
  for (final rel in (await _listBlobs(store, fromPrefix)).keys) {
    await store.deleteFile('$fromPrefix/$rel', message: 'e2e cleanup');
  }
  return true;
}
