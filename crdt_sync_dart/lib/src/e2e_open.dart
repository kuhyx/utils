/// Opens the encrypted store for an app whose old plaintext prefix is
/// [oldPrefix]; data lives on `E2eLayout.of(oldPrefix)`.
///
/// [readPassphrase] supplies the shared crdt-sync passphrase from the OS
/// keystore, so the open is prompt-free. Fail closed: a missing or wrong
/// passphrase, or an unreadable header, returns [E2eLocked] and the caller
/// must not sync. On success the old plaintext prefix is copied over
/// (idempotent; picks up writes from builds not yet migrated) and is never
/// deleted here.
library;

import 'dart:developer';

import 'e2e_key.dart';
import 'e2e_migration.dart';
import 'remote_store.dart';
import 'sync.dart';

/// Keystore entry name apps store the shared passphrase under.
const String kE2ePassphraseStorageKey = 'crdt_sync_e2e_passphrase';

/// Where a device keeps its derived 32-byte key, so Argon2id runs once per
/// device rather than once per sync tick. Back it with the OS keystore.
class E2eKeyCache {
  /// Creates a cache from [read] and [write] closures.
  const E2eKeyCache({required this.read, required this.write});

  /// Returns the cached key bytes, or null.
  final Future<List<int>?> Function() read;

  /// Stores freshly derived key bytes.
  final Future<void> Function(List<int> bytes) write;
}

/// Old-prefix revision fingerprints already copied, per old prefix.
final Map<String, String> _copied = {};

/// Forgets which old prefixes were copied; for tests.
void resetE2eCopyMemo() => _copied.clear();

Future<String> _oldFingerprint(RemoteStore store, String oldPrefix) async {
  if (store is! BulkMapReader) return '';
  try {
    final revs = await (store as BulkMapReader).getStringMap(
      defaultRevsPath(oldPrefix),
    );
    final keys = revs.keys.toList()..sort();
    return [for (final k in keys) '$k=${revs[k]}'].join(';');
  } on Object {
    return '';
  }
}

Future<E2eReady?> _tryCached(
  RemoteStore store,
  E2eLayout layout,
  E2eKeyCache? cache,
) async {
  final bytes = await cache?.read();
  if (bytes == null || bytes.length != 32) return null;
  final state = await openE2e(
    store: store,
    pathPrefix: layout.prefix,
    key: await E2eKey.fromBytes(bytes),
    e2ePath: layout.e2ePath,
    revsPath: layout.revsPath,
  );
  return state is E2eReady ? state : null;
}

/// Opens the encrypted store; see the library doc.
///
/// [keyCache] skips Argon2id when it holds the key for the current header.
/// The one-time copy reruns only when the old prefix's published revisions
/// change (or once per process where the backend cannot bulk-read them).
/// [onDerive] is called each time Argon2id actually runs; for tests.
Future<E2eState> openEncryptedStore({
  required RemoteStore store,
  required String oldPrefix,
  required Future<String?> Function() readPassphrase,
  Argon2Params params = Argon2Params.recommended,
  E2eKeyCache? keyCache,
  void Function()? onDerive,
}) async {
  final layout = E2eLayout.of(oldPrefix);
  final E2eReady ready;
  final E2eReady? cached;
  try {
    cached = await _tryCached(store, layout, keyCache);
  } on E2eHeaderError {
    return E2eLocked(E2eLockReason.badHeader);
  }
  if (cached != null) {
    ready = cached;
  } else {
    final passphrase = await readPassphrase();
    if (passphrase == null || passphrase.isEmpty) {
      return E2eLocked(E2eLockReason.needsPassphrase);
    }
    final E2eKey key;
    try {
      onDerive?.call();
      key = await unlockE2e(
        store: store,
        pathPrefix: layout.prefix,
        passphrase: passphrase,
        params: params,
        e2ePath: layout.e2ePath,
      );
    } on E2eWrongPassphraseError {
      return E2eLocked(E2eLockReason.wrongKey);
    } on E2eHeaderError {
      return E2eLocked(E2eLockReason.badHeader);
    }
    await keyCache?.write(key.bytes);
    final state = await openE2e(
      store: store,
      pathPrefix: layout.prefix,
      key: key,
      e2ePath: layout.e2ePath,
      revsPath: layout.revsPath,
    );
    if (state is! E2eReady) return state;
    ready = state;
  }
  try {
    final print = await _oldFingerprint(store, oldPrefix);
    if (_copied[oldPrefix] != print) {
      await copyToEncrypted(
        store: store,
        key: ready.store.key,
        fromPrefix: oldPrefix,
        layout: layout,
      );
      _copied[oldPrefix] = print;
    }
  } on Object catch (error, stackTrace) {
    // The copy is retried next open; sync itself must not stop for it.
    log('e2e copy failed', level: 900, error: error, stackTrace: stackTrace);
  }
  return ready;
}
