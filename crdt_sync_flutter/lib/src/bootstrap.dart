/// Opening a signed-in Firebase client, in one call.
///
/// This is the file an adopting app no longer writes. Give it the project
/// identifiers and it handles the rest: the keystore, the stored refresh
/// token, the sign-in that only happens when there is no session, and the
/// recovery path for a device holding a session with no account marker.
library;

import 'dart:developer';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:crdt_sync_flutter/src/account_store.dart';
import 'package:crdt_sync_flutter/src/keystore.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

/// Everything an app must supply to sync: the public project identifiers,
/// the uid the security rules pin, and where its desktop wrapper serves
/// seeded credentials from.
///
/// [project] and [expectedUid] are safe to hold in source. The repos are
/// public and the Web API key ships inside every APK: the security rules,
/// not secrecy, are what protect the data. The account email and password
/// are not here, and never belong in source.
class SyncApp {
  /// Creates an app descriptor.
  const SyncApp({
    required this.project,
    required this.expectedUid,
    this.routes,
  });

  /// Public project identifiers (API key + regional database URL).
  final FirebaseProject project;

  /// The uid the rules pin.
  ///
  /// Load-bearing: `signInWithIdp` signs in *or signs up*, so an unlinked
  /// Google account is accepted as a new uid, authenticates fine, and is then
  /// denied every read and write -- a sync that silently never syncs.
  final String expectedUid;

  /// This app's desktop wrapper routes, or null when it has none.
  final WrapperRoutes? routes;
}

/// Returns a signed-in client, or null when this device is not configured.
///
/// Not being set up is a normal state, not an error: the caller keeps working
/// against its local store and simply does not sync.
///
/// Deliberately does **not** offer Google sign-in. This runs from background
/// ticks and, in some apps, before `runApp`; offering Google there would
/// raise the OS account picker with no user action behind it. Interactive
/// sign-in goes through [signInWithGoogle].
Future<FirebaseRestClient?> openSync(
  SyncApp app, {
  http.Client? httpClient,
  FlutterSecureStorage storage = kSecureStorage,
}) async {
  final account = await loadAccount(
    routes: app.routes,
    httpClient: httpClient,
    storage: storage,
  );
  if (account == null) {
    // A stored refresh token IS a signed-in device, even with no account
    // marker beside it. Treating the marker as the source of truth made a
    // phone with a live session sync over the mirror and fail forever.
    return _clientFromStoredSession(app, storage: storage);
  }
  return firebaseClientFor(
    config: app.project.configFor(account.email),
    store: keystoreCredentialStore(storage: storage),
    // A Google-provisioned account stores an empty password. Passing ''
    // would make firebaseClientFor treat it as usable and sign in with it,
    // which fails; null correctly means "no password on this device".
    password: account.password.isEmpty ? null : account.password,
    expectedUid: app.expectedUid,
    httpClient: httpClient,
  );
}

/// Signs in with Google alone, for a device with no account stored yet.
///
/// The one-tap path: [openSync] needs an account to know which email to use,
/// but a fresh install has none. [tokenFetcher] is the app's `google_sign_in`
/// call -- a closure because that plugin is Android/iOS/web only and this
/// package must keep working on Linux desktop.
///
/// Returns null when the user dismisses the picker; throws
/// [FirebaseAuthError] when Google succeeds but resolves to the wrong uid,
/// which is a misconfiguration worth surfacing rather than swallowing.
Future<FirebaseRestClient?> signInWithGoogle(
  SyncApp app, {
  required Future<String?> Function() tokenFetcher,
  http.Client? httpClient,
  FlutterSecureStorage storage = kSecureStorage,
}) async {
  final token = await tokenFetcher();
  if (token == null) return null;
  final auth = FirebaseTokenProvider(
    apiKey: app.project.apiKey,
    store: keystoreCredentialStore(storage: storage),
    httpClient: httpClient,
  );
  final email = await auth.signInWithGoogle(
    idToken: token,
    expectedUid: app.expectedUid,
  );
  // Saved unconditionally, and deliberately not gated on `email`:
  // signInWithIdp omits that field whenever the Google account hides it, and
  // gating the write on it returned a working client while persisting
  // nothing, so the next launch looked unconfigured. The refresh token, not
  // the address, is the credential -- and it is already durable here.
  await saveAccount(
    FirebaseAccount(email: email ?? '', password: ''),
    storage: storage,
  );
  return FirebaseRestClient(
    databaseUrl: app.project.databaseUrl,
    auth: auth,
    httpClient: httpClient,
  );
}

/// Whether this device can actually authenticate.
///
/// True when a session exists. A marker alone is not enough: a revoked
/// refresh token makes the library clear the session, and a marker left
/// behind would report "Connected" while every sync failed. So when a marker
/// outlives its session, the marker is the stale half -- drop it.
Future<bool> isSyncConfigured(
  SyncApp app, {
  FlutterSecureStorage storage = kSecureStorage,
}) async {
  try {
    final auth = FirebaseTokenProvider(
      apiKey: app.project.apiKey,
      store: keystoreCredentialStore(storage: storage),
    );
    if (await auth.hasSession()) return true;
    if (await storedAccount(storage: storage) == null) return false;
    await clearAccountMarkerOnly(storage: storage);
    return false;
  } on Object catch (error, stackTrace) {
    log(
      'session probe failed; reporting this device as not configured',
      level: 1000,
      error: error,
      stackTrace: stackTrace,
    );
    return false;
  }
}

/// Builds a client from the keystore's refresh token alone, or null.
///
/// Deliberately has no catch of its own. Both steps it takes are already
/// total: `hasSession` reads through [SecureCredentialStore.load], which
/// converts a throwing keystore into a null session, and the client's
/// constructor does no I/O -- a bad database URL surfaces on the first
/// request, not here. A `catch` around this would be a branch no input can
/// reach, and therefore one no test can cover.
Future<FirebaseRestClient?> _clientFromStoredSession(
  SyncApp app, {
  FlutterSecureStorage storage = kSecureStorage,
}) async {
  final auth = FirebaseTokenProvider(
    apiKey: app.project.apiKey,
    store: keystoreCredentialStore(storage: storage),
  );
  if (!await auth.hasSession()) return null;
  return FirebaseRestClient(
    databaseUrl: app.project.databaseUrl,
    auth: auth,
  );
}
