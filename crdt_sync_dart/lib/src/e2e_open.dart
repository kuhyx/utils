/// Opens the encrypted store for an app whose old plaintext prefix is
/// [oldPrefix]; data lives on `E2eLayout.of(oldPrefix)`.
///
/// [readPassphrase] supplies the shared crdt-sync passphrase from the OS
/// keystore, so the open is prompt-free. Fail closed: a missing or wrong
/// passphrase, or an unreadable header, returns [E2eLocked] and the caller
/// must not sync. On success the old plaintext prefix is copied over once
/// per call (idempotent; picks up writes from builds not yet migrated) and
/// is never deleted here.
library;

import 'dart:developer';

import 'e2e_key.dart';
import 'e2e_migration.dart';
import 'remote_store.dart';

/// Keystore entry name apps store the shared passphrase under.
const String kE2ePassphraseStorageKey = 'crdt_sync_e2e_passphrase';

Future<E2eState> openEncryptedStore({
  required RemoteStore store,
  required String oldPrefix,
  required Future<String?> Function() readPassphrase,
  Argon2Params params = Argon2Params.recommended,
}) async {
  final passphrase = await readPassphrase();
  if (passphrase == null || passphrase.isEmpty) {
    return E2eLocked(E2eLockReason.needsPassphrase);
  }
  final layout = E2eLayout.of(oldPrefix);
  final E2eKey key;
  try {
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
  try {
    await copyToEncrypted(
      store: store,
      key: key,
      fromPrefix: oldPrefix,
      layout: layout,
    );
  } on Object catch (error, stackTrace) {
    // The copy is retried next open; sync itself must not stop for it.
    log('e2e copy failed', level: 900, error: error, stackTrace: stackTrace);
  }
  return await openE2e(
    store: store,
    pathPrefix: layout.prefix,
    key: key,
    e2ePath: layout.e2ePath,
    revsPath: layout.revsPath,
  );
}
