/// End-to-end encryption for an app's sync prefix, keyed by the shared
/// crdt-sync passphrase kept in the OS keystore (prompt-free after setup).
library;

import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:crdt_sync_flutter/src/keystore.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Keystore key holding the shared crdt-sync passphrase.
const String kE2ePassphraseKey = kE2ePassphraseStorageKey;

/// Stores the passphrase this device derives its key from, dropping keys
/// cached from an earlier one so the new passphrase is what gets checked.
Future<void> saveE2ePassphrase(
  String passphrase, {
  FlutterSecureStorage storage = kSecureStorage,
}) async {
  await _dropCachedKeys(storage);
  await storage.write(key: kE2ePassphraseKey, value: passphrase);
}

Future<void> _dropCachedKeys(FlutterSecureStorage storage) async {
  final all = await storage.readAll();
  for (final key in all.keys) {
    if (key.startsWith(kE2eKeyCachePrefix)) await storage.delete(key: key);
  }
}

/// Keystore key prefix for derived keys, one per old prefix.
const String kE2eKeyCachePrefix = 'crdt_sync_e2e_key:';

/// Forgets the passphrase and every cached key; the next open is locked.
Future<void> clearE2ePassphrase({
  FlutterSecureStorage storage = kSecureStorage,
}) async {
  await storage.delete(key: kE2ePassphraseKey);
  await _dropCachedKeys(storage);
}

/// The derived key for [oldPrefix], cached in the OS keystore so Argon2id
/// runs once per device instead of on every sync tick.
E2eKeyCache keystoreKeyCache(
  String oldPrefix, {
  FlutterSecureStorage storage = kSecureStorage,
}) {
  final name = '$kE2eKeyCachePrefix$oldPrefix';
  return E2eKeyCache(
    read: () async {
      final text = await storage.read(key: name);
      if (text == null) return null;
      try {
        return base64.decode(text);
      } on FormatException {
        return null;
      }
    },
    write: (bytes) => storage.write(key: name, value: base64.encode(bytes)),
  );
}

/// [openEncryptedStore] reading the passphrase from the OS keystore.
Future<E2eState> openEncryptedStoreFromKeystore({
  required RemoteStore store,
  required String oldPrefix,
  FlutterSecureStorage storage = kSecureStorage,
  Argon2Params params = Argon2Params.recommended,
  void Function()? onDerive,
}) => openEncryptedStore(
  store: store,
  oldPrefix: oldPrefix,
  readPassphrase: () => storage.read(key: kE2ePassphraseKey),
  params: params,
  keyCache: keystoreKeyCache(oldPrefix, storage: storage),
  onDerive: onDerive,
);
