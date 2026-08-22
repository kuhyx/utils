/// Reading, writing and forgetting the per-device Firebase account.
///
/// This is the file that had drifted. Four apps carried near-identical copies
/// of it; `todo` gained an opt-out flag and a seeded-session path that
/// `home_inventory` and `wake_alarm` never received, so the same bug was
/// fixed in one copy and left live in the others. Owning it here means the
/// next fix lands everywhere at once.
///
/// Nothing here reads `~/.config/crdt-sync/` directly -- that is the
/// desktop/Python half, reached over the local wrapper's HTTP routes. On
/// Android no such file exists.
library;

import 'dart:convert';
import 'dart:developer';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:crdt_sync_flutter/src/keystore.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

/// Where a desktop install can fetch a seeded session from its own wrapper.
///
/// Per-app, because each app's wrapper serves its own seeded file: the
/// `todo` app's lives at `~/.config/todo/firebase_auth.json`, written by
/// `seed_session.py`. An app with no desktop wrapper passes null and the
/// whole fallback
/// is skipped -- which is what Android does in practice, since `Uri.base`
/// there is `file:///` and has no host to request from.
class WrapperRoutes {
  /// Creates a route set.
  const WrapperRoutes({required this.credentialsPath, this.accountPath});

  /// Path serving the seeded Firebase session, e.g. `/sync-credentials`.
  final String credentialsPath;

  /// Path serving the legacy email/password pair, e.g. `/sync-account`.
  ///
  /// Null where the app never had one. The shared account's password grant is
  /// retired fleet-wide, so this exists only for machines not yet re-seeded.
  final String? accountPath;
}

/// Reads the per-device account, or null when sync is not set up here.
///
/// Order: the keystore, then -- only when [routes] is given and the user has
/// not disconnected -- the seeded session, then the legacy password route.
/// Whichever succeeds is written to the keystore, so a fallback is consulted
/// once rather than staying load-bearing forever.
Future<FirebaseAccount?> loadAccount({
  WrapperRoutes? routes,
  Uri? base,
  http.Client? httpClient,
  FlutterSecureStorage storage = kSecureStorage,
}) async {
  try {
    final stored = FirebaseAccount.tryParse(
      await storage.read(key: kAccountKey),
    );
    if (stored != null) return stored;
    // Disconnect must stick: without this the next launch silently re-adopts
    // the account and the disconnect button looks broken.
    if (await storage.read(key: kOptOutKey) != null) return null;
    if (routes == null) return null;
    final origin = base ?? Uri.base;
    final seeded = await _adoptSeededSession(
      origin,
      routes,
      client: httpClient,
      storage: storage,
    );
    if (seeded != null) return seeded;
    final path = routes.accountPath;
    if (path == null) return null;
    final provisioned = await accountFromWrapper(origin, client: httpClient);
    if (provisioned != null) {
      await saveAccount(provisioned, storage: storage);
    }
    return provisioned;
    // Broader than Exception on purpose: on Android `Uri.base` is `file:///`
    // and the request raises ArgumentError ("No host specified in URI") --
    // an Error, which `on Exception` does not catch. That escaped the caller
    // and killed the whole sync tick, so a signed-in phone pulled nothing.
  } on Object catch (error, stackTrace) {
    // Still "not configured" rather than a crash -- but never silent: hiding
    // why provisioning failed makes it indistinguishable from "no account".
    log(
      'loadAccount failed; treating this device as not configured',
      level: 1000,
      error: error,
      stackTrace: stackTrace,
    );
    return null;
  }
}

/// Adopts a seeded session from the wrapper: stores the refresh token and
/// writes an account marker so settings shows an address, not a blank.
///
/// Returns null on any failure -- route disabled, file absent, malformed
/// body, no wrapper at all -- because the caller's fallback is simply "not
/// configured".
Future<FirebaseAccount?> _adoptSeededSession(
  Uri base,
  WrapperRoutes routes, {
  http.Client? client,
  FlutterSecureStorage storage = kSecureStorage,
}) async {
  final httpClient = client ?? http.Client();
  try {
    final response = await httpClient.get(
      base.resolve(routes.credentialsPath),
    );
    if (response.statusCode != 200) return null;
    final body = jsonDecode(utf8.decode(response.bodyBytes));
    if (body is! Map<String, dynamic>) return null;
    if (body['id_token'] is! String ||
        body['refresh_token'] is! String ||
        body['expires_at'] is! String) {
      return null;
    }
    await keystoreCredentialStore(
      storage: storage,
    ).save(FirebaseCredentials.fromJson(body));
    final email = body['email'];
    final account = FirebaseAccount(
      email: email is String ? email : '',
      password: '',
    );
    await saveAccount(account, storage: storage);
    return account;
  } on Exception {
    return null;
  } finally {
    if (client == null) httpClient.close();
  }
}

/// Reads the account from the keystore only, with no wrapper fallback.
///
/// Callers that only want to read back an account they just wrote use this:
/// on Android the fallback resolves to `file:///` and throws, which turned a
/// successful sign-in into a reported failure.
Future<FirebaseAccount?> storedAccount({
  FlutterSecureStorage storage = kSecureStorage,
}) async => FirebaseAccount.tryParse(await storage.read(key: kAccountKey));

/// Stores the per-device account. Keystore only -- never prefs, never source.
Future<void> saveAccount(
  FirebaseAccount account, {
  FlutterSecureStorage storage = kSecureStorage,
}) => storage.write(key: kAccountKey, value: account.toJsonString());

/// Forgets the account and any cached session, and suppresses re-adoption.
Future<void> clearAccount({
  FlutterSecureStorage storage = kSecureStorage,
}) async {
  await storage.delete(key: kAccountKey);
  await storage.write(key: kOptOutKey, value: 'true');
  await keystoreCredentialStore(storage: storage).clear();
}

/// Drops the account marker alone, leaving the opt-out flag unset.
///
/// For a marker found with no session behind it: [clearAccount] would also
/// set the opt-out flag and stop the wrapper re-provisioning after the next
/// sign-in.
Future<void> clearAccountMarkerOnly({
  FlutterSecureStorage storage = kSecureStorage,
}) => storage.delete(key: kAccountKey);
