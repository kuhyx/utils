/// The OS-keystore adapter every consuming app was writing by hand.
///
/// `crdt_sync` is pure Dart on purpose -- it runs from command-line tools and
/// headless systemd jobs -- so it cannot depend on `flutter_secure_storage`
/// and instead takes read/write/delete closures. Every Flutter app then wrote
/// the same three-line adapter, and four of them now differ only in which
/// bugs they have had fixed.
///
/// This file owns that adapter once.
library;

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Storage options shared with the GitHub token these apps already keep.
///
/// Off Android's deprecated `encryptedSharedPreferences` path, and libsecret
/// on Linux.
const FlutterSecureStorage kSecureStorage = FlutterSecureStorage();

/// Key the account blob (email + password) is stored under.
const String kAccountKey = kFirebaseAccountKey;

/// Key set when the user disconnects, to stop silent re-provisioning.
///
/// Without it the next launch re-adopts the account from whatever fallback is
/// available and the disconnect button looks broken.
const String kOptOutKey = kSyncAccountOptOutKey;

/// A [FirebaseCredentialStore] over the platform keystore.
///
/// Pass [storage] only in tests; production uses [kSecureStorage].
FirebaseCredentialStore keystoreCredentialStore({
  FlutterSecureStorage storage = kSecureStorage,
}) => SecureCredentialStore(
  read: (key) => storage.read(key: key),
  write: (key, value) => storage.write(key: key, value: value),
  delete: (key) => storage.delete(key: key),
);
