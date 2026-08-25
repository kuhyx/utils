import 'dart:developer';

import 'package:crdt_sync/crdt_sync.dart';

/// Outcome of a Firebase connect attempt, distinguishing why it did or did
/// not end connected -- the UI needs different copy for each case, and
/// collapsing them lost that distinction in the app-local copies this
/// generalizes.
enum FirebaseConnectOutcome {
  /// Signed in and the session is confirmed stored.
  connected,

  /// The client rejected the given account (bad password / wrong account).
  rejected,

  /// The user dismissed the Google picker. Not an error.
  cancelled,

  /// Google signed in, but this device did not end up with a stored
  /// session -- the client came back non-null yet [FirebaseSyncController]
  /// re-reads state rather than trusting that, and found nothing durable.
  signedInButNotPersisted,

  /// Google succeeded but resolved to a uid the security rules do not pin
  /// (wrong account entirely).
  wrongAccount,

  /// Any other failure (network, unreachable keystore, etc).
  failed,
}

/// Result of a [FirebaseSyncController.connectWithPassword] or
/// [FirebaseSyncController.connectWithGoogle] call.
class FirebaseConnectResult {
  /// Creates a [FirebaseConnectResult].
  const FirebaseConnectResult({
    required this.outcome,
    this.email,
    this.message,
  });

  /// What happened.
  final FirebaseConnectOutcome outcome;

  /// The connected account's email, when known.
  final String? email;

  /// Human-readable detail for [FirebaseConnectOutcome.failed] and
  /// [FirebaseConnectOutcome.wrongAccount].
  final String? message;
}

/// Sequences Firebase connect/disconnect/status-probe over injected
/// closures, generalized from the near-identical `_connectFirebase` /
/// `_connectGoogle` / `_disconnectFirebase` / `_load` logic duplicated
/// across every app's settings screen.
///
/// Deliberately holds no keystore or `google_sign_in` reference itself --
/// every constructor parameter is the same closure each app's
/// `SettingsScreen` already built around its own `firebase_backend.dart` /
/// `google_sign_in_backend.dart`. That keeps this class pure Dart and fully
/// unit-testable with fakes, with the actual platform-channel adapters
/// staying in the app where they were already `// coverage:ignore`d for
/// being unreachable from `flutter test`.
class FirebaseSyncController {
  /// Creates a [FirebaseSyncController] over the app's injected Firebase
  /// wiring. See each field's doc for what it does; [googleFirebaseFactory]
  /// is optional because Google sign-in itself is optional per
  /// app/platform (see `googleAvailable` on `SyncSettingsScreen`) --
  /// [connectWithGoogle] must not be called when it is null.
  FirebaseSyncController({
    required this.accountLoader,
    required this.accountSaver,
    required this.accountClearer,
    required this.sessionProbe,
    required this.firebaseFactory,
    this.googleFirebaseFactory,
  });

  /// Reads the stored Firebase account, or null when sync has not been set
  /// up on this device.
  final Future<FirebaseAccount?> Function() accountLoader;

  /// Persists the account. See [accountLoader].
  final Future<void> Function(FirebaseAccount) accountSaver;

  /// Forgets the account and any cached session. See [accountLoader].
  final Future<void> Function() accountClearer;

  /// Whether a Firebase session is stored.
  ///
  /// Separate from [accountLoader] because the two answer different
  /// questions: the account marker is bookkeeping, the session is the
  /// credential. A device can hold the second without the first, and
  /// reporting only the first is what made a syncing phone read as "not
  /// connected".
  final Future<bool> Function() sessionProbe;

  /// Builds the Firebase backend from the stored account.
  final Future<FirebaseRestClient?> Function() firebaseFactory;

  /// Builds the Firebase backend via Google sign-in. Optional because
  /// Google sign-in itself is optional per app/platform (see
  /// `googleAvailable` on `SyncSettingsScreen`); [connectWithGoogle] must
  /// not be called when this is null.
  final Future<FirebaseRestClient?> Function()? googleFirebaseFactory;

  /// Whether [connectWithGoogle] can be called.
  bool get supportsGoogle => googleFirebaseFactory != null;

  /// Reads whether this device currently reports a connected Firebase
  /// session, and the account email if any is stored.
  ///
  /// Deliberately trusts the session probe (the stored session), never a
  /// client's mere non-null return value, for "connected": the invariant
  /// every app's `firebase_backend.dart` documents as
  /// "read back the stored session, don't trust the returned client" --
  /// a session probe built on `hasSession()` treats a live refresh token as
  /// connected even with no account marker beside it, while a marker with no
  /// session behind it (a revoked token) is the stale half and must read as
  /// *not* connected. Trusting a freshly-returned client instead is exactly
  /// what let a signed-in-but-not-actually-persisted device claim
  /// "Connected" and then sync over the GitHub mirror and 401 forever.
  Future<({bool connected, String? email})> loadStatus() async {
    final account = await accountLoader();
    final connected = await sessionProbe();
    return (connected: connected, email: account?.email);
  }

  /// Stores [email]/[password] and signs in immediately, so a typo surfaces
  /// here instead of as a silent background failure on the next sync tick.
  ///
  /// [onProgress], if given, is called with a human-readable stage name as
  /// each awaited step starts, so a caller can show the user what is
  /// actually happening instead of one static "Signing in..." the whole
  /// time -- and, if it stalls, which step it stalled on.
  ///
  /// Wraps [firebaseFactory] the same way [connectWithGoogle] already does:
  /// broader than Exception on purpose, matching every app-local copy -- a
  /// missing platform binding raises a FlutterError, which is an Error, not
  /// an Exception -- letting it escape left the button disabled and the
  /// screen stuck on "Signing in..." forever. That fix existed for the
  /// Google path but was never mirrored here.
  Future<FirebaseConnectResult> connectWithPassword({
    required String email,
    required String password,
    void Function(String stage)? onProgress,
  }) async {
    onProgress?.call('Saving account…');
    await accountSaver(FirebaseAccount(email: email, password: password));
    try {
      onProgress?.call('Signing in to Firebase…');
      final client = await firebaseFactory();
      if (client == null) {
        log(
          'connectWithPassword: rejected (null client) for $email',
          name: 'FirebaseSyncController',
          level: 900,
        );
        await accountClearer();
        return const FirebaseConnectResult(
          outcome: FirebaseConnectOutcome.rejected,
        );
      }
      log(
        'connectWithPassword: connected as $email',
        name: 'FirebaseSyncController',
      );
      return FirebaseConnectResult(
        outcome: FirebaseConnectOutcome.connected,
        email: email,
      );
    } on FirebaseAuthError catch (error, stackTrace) {
      log(
        'connectWithPassword: rejected for $email',
        name: 'FirebaseSyncController',
        level: 900,
        error: error,
        stackTrace: stackTrace,
      );
      // A confirmed-bad password shouldn't linger in the keystore for a
      // background sync tick to keep retrying against.
      await accountClearer();
      return FirebaseConnectResult(
        outcome: FirebaseConnectOutcome.rejected,
        message: error.message,
      );
    } on Object catch (error, stackTrace) {
      log(
        'connectWithPassword: failed for $email',
        name: 'FirebaseSyncController',
        level: 1000,
        error: error,
        stackTrace: stackTrace,
      );
      // Not cleared: this could be a transient failure (network, wrapper
      // hiccup), not proof the credentials themselves are wrong.
      return FirebaseConnectResult(
        outcome: FirebaseConnectOutcome.failed,
        message: '$error',
      );
    }
  }

  /// Signs in by picking a Google account -- the one-tap path. Callers must
  /// check [supportsGoogle] first.
  ///
  /// Distinguishes outcomes the same way the app-local copies did: a
  /// dismissed picker is not an error; a wrong-account sign-in reports why,
  /// because that failure would otherwise look like a working sync that
  /// never actually syncs; anything else not caught by [FirebaseAuthError]
  /// is a plain failure. Reports the persisted state via the session probe
  /// after the call, not the fact that a client came back -- see
  /// [loadStatus]'s doc for why that distinction matters.
  Future<FirebaseConnectResult> connectWithGoogle() async {
    final googleFactory = googleFirebaseFactory;
    if (googleFactory == null) {
      throw StateError(
        'connectWithGoogle() called without a googleFirebaseFactory; '
        'check supportsGoogle first.',
      );
    }
    try {
      final client = await googleFactory();
      if (client == null) {
        return const FirebaseConnectResult(
          outcome: FirebaseConnectOutcome.cancelled,
        );
      }
      final account = await accountLoader();
      final connected = await sessionProbe();
      if (!connected) {
        return FirebaseConnectResult(
          outcome: FirebaseConnectOutcome.signedInButNotPersisted,
          email: account?.email,
        );
      }
      return FirebaseConnectResult(
        outcome: FirebaseConnectOutcome.connected,
        email: account?.email,
      );
    } on FirebaseAuthError catch (error) {
      return FirebaseConnectResult(
        outcome: FirebaseConnectOutcome.wrongAccount,
        message: error.message,
      );
      // Broader than Exception on purpose, matching every app-local copy:
      // a missing platform binding raises a FlutterError, which is an
      // Error, not an Exception -- letting it escape left the button
      // disabled and the screen stuck on "Signing in..." forever on the
      // phone.
    } on Object catch (error) {
      return FirebaseConnectResult(
        outcome: FirebaseConnectOutcome.failed,
        message: '$error',
      );
    }
  }

  /// Forgets the account and any cached session.
  Future<void> disconnect() => accountClearer();
}
