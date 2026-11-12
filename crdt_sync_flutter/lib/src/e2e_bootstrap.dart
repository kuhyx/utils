/// End-to-end encryption for an app's sync prefix, keyed by the shared
/// crdt-sync passphrase kept in the OS keystore (prompt-free after setup).
library;

import 'package:crdt_sync/crdt_sync.dart';
import 'package:crdt_sync_flutter/src/keystore.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Keystore key holding the shared crdt-sync passphrase.
const String kE2ePassphraseKey = kE2ePassphraseStorageKey;

/// Stores the passphrase this device derives its key from.
Future<void> saveE2ePassphrase(
  String passphrase, {
  FlutterSecureStorage storage = kSecureStorage,
}) => storage.write(key: kE2ePassphraseKey, value: passphrase);

/// Forgets the passphrase; the next open is locked.
Future<void> clearE2ePassphrase({
  FlutterSecureStorage storage = kSecureStorage,
}) => storage.delete(key: kE2ePassphraseKey);

/// [openEncryptedStore] reading the passphrase from the OS keystore.
Future<E2eState> openEncryptedStoreFromKeystore({
  required RemoteStore store,
  required String oldPrefix,
  FlutterSecureStorage storage = kSecureStorage,
  Argon2Params params = Argon2Params.recommended,
}) => openEncryptedStore(
  store: store,
  oldPrefix: oldPrefix,
  readPassphrase: () => storage.read(key: kE2ePassphraseKey),
  params: params,
);
