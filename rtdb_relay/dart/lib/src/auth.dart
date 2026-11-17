/// The signed-in session: Google ID token -> Firebase refresh token in the
/// keystore -> short-lived ID tokens for every RTDB request.
///
/// "Connected" means a stored session (refresh token), never an account
/// marker: that confusion kept phones "not connected" while their credential
/// sat unused in the keystore (todo, 2026-08-11).
library;

import 'dart:developer';

import 'package:crdt_sync/crdt_sync.dart'
    show
        FirebaseAuthError,
        FirebaseCredentialStore,
        FirebaseTokenProvider,
        SecureCredentialStore;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

/// Outcome of an interactive sign-in.
enum SignInOutcome {
  /// A session is stored; the app can sync.
  signedIn,

  /// The user dismissed the picker, or Google sign-in is unavailable.
  cancelled,
}

/// The Firebase identifiers an app build talks to. Keep the literal values
/// out of public source (a gitignored generated file).
class RelayFirebaseConfig {
  /// Creates a config; tests pass fakes.
  const new({
    required this.apiKey,
    required this.databaseUrl,
    required this.syncUid,
    required this.serverClientId,
  });

  /// Web API key of the Firebase project.
  final String apiKey;

  /// Regional RTDB URL.
  final String databaseUrl;

  /// The uid the sync account must resolve to. A wrong Google account signs
  /// up a second user; this guard refuses it before anything is stored.
  final String syncUid;

  /// Google *Web* OAuth client id, used as the ID-token audience.
  final String serverClientId;
}

/// Fetches a Google ID token for [serverClientId]'s audience; null when the
/// user cancelled or sign-in is unavailable. crdt_sync_flutter's
/// `googleIdToken` fits.
typedef GoogleTokenFetcher = Future<String?> Function({
  required String serverClientId,
});

/// Owns the Firebase session for this install.
class RelayAuth {
  /// Creates the auth wrapper. Tests pass a memory [store] and fake [http].
  new({
    required this.config,
    required this.googleToken,
    required FirebaseCredentialStore store,
    http.Client? httpClient,
    DateTime Function()? clock,
    this.adopt,
  }) : provider = FirebaseTokenProvider(
         apiKey: config.apiKey,
         store: store,
         httpClient: httpClient,
         clock: clock,
       );

  /// Desktop only: adopts the PC's seeded session from the wrapper when
  /// no session is stored (see `wrapper_credentials.dart`). True if adopted.
  final Future<bool> Function()? adopt;

  /// The build's Firebase identifiers.
  final RelayFirebaseConfig config;

  /// The interactive Google sign-in.
  final GoogleTokenFetcher googleToken;

  /// Mints ID tokens, refreshing from the stored refresh token.
  final FirebaseTokenProvider provider;

  /// Whether a session is stored. Never throws: an unreadable store reads
  /// as "not signed in", and the sign-in screen repairs it.
  Future<bool> hasSession() async {
    try {
      if (await provider.hasSession()) return true;
      final adopt = this.adopt;
      return adopt != null && await adopt() && await provider.hasSession();
    } on Object catch (error, stackTrace) {
      // `on Object`: an ArgumentError (Uri.base on Android) is an Error, not
      // an Exception, and escaped `on Exception` in todo.
      log(
        'session probe failed; treating as signed out',
        level: 1000,
        error: error,
        stackTrace: stackTrace,
      );
      return false;
    }
  }

  /// Interactive Google sign-in with the expected-uid guard.
  ///
  /// Throws [FirebaseAuthError] when Google resolves to a different uid:
  /// picking the wrong account would otherwise silently sign up a second
  /// user. Nothing is stored in that case.
  Future<SignInOutcome> signInWithGoogle({
    Future<String?> Function()? tokenFetcher,
  }) async {
    final token =
        await (tokenFetcher ??
            () => googleToken(serverClientId: config.serverClientId))();
    if (token == null) return SignInOutcome.cancelled;
    await provider.signInWithGoogle(
      idToken: token,
      expectedUid: config.syncUid,
    );
    return SignInOutcome.signedIn;
  }

  /// A currently valid ID token; throws [FirebaseAuthError] when signed out
  /// or the refresh token was revoked (the session is then cleared).
  Future<String> idToken() => provider.idToken();

  /// Forgets the stored session.
  Future<void> signOut() => provider.signOut();
}

/// The keystore-backed credential store (Android keystore; web storage)
/// under [key] (e.g. `tutor.firebase.credentials`).
// coverage:ignore-start
FirebaseCredentialStore secureCredentialStore(String key) {
  const secure = FlutterSecureStorage();
  return SecureCredentialStore(
    read: (k) => secure.read(key: k),
    write: (k, v) => secure.write(key: k, value: v),
    delete: (k) => secure.delete(key: k),
    key: key,
  );
}
// coverage:ignore-end
