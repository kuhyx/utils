/// End-to-end encryption for an app's sync prefix, keyed by the shared
/// crdt-sync passphrase kept in the OS keystore (prompt-free after setup).
library;

import 'dart:developer';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:crdt_sync_flutter/src/keystore.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Keystore key holding the shared crdt-sync passphrase.
const String kE2ePassphraseKey = 'crdt_sync_e2e_passphrase';

/// Stores the passphrase this device derives its key from.
Future<void> saveE2ePassphrase(
  String passphrase, {
  FlutterSecureStorage storage = kSecureStorage,
}) => storage.write(key: kE2ePassphraseKey, value: passphrase);

/// Forgets the passphrase; the next open is locked.
Future<void> clearE2ePassphrase({
  FlutterSecureStorage storage = kSecureStorage,
}) => storage.delete(key: kE2ePassphraseKey);

/// Opens the encrypted store for [oldPrefix] (the app's former plaintext
/// prefix; data lives on `E2eLayout.of(oldPrefix)`).
///
/// Fail closed: no passphrase, a wrong one, or an unreadable header returns
/// [E2eLocked] and the caller must not sync (show an icon-only lock state).
/// On success the old plaintext prefix is copied over once per call, which is
/// idempotent and picks up writes from builds not yet migrated; the old
/// prefix is never deleted here.
Future<E2eState> openEncryptedStore({
  required RemoteStore store,
  required String oldPrefix,
  FlutterSecureStorage storage = kSecureStorage,
  Argon2Params params = Argon2Params.recommended,
}) async {
  final passphrase = await storage.read(key: kE2ePassphraseKey);
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
  return openE2e(
    store: store,
    pathPrefix: layout.prefix,
    key: key,
    e2ePath: layout.e2ePath,
    revsPath: layout.revsPath,
  );
}
