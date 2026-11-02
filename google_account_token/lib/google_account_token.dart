/// One-tap Google ID token on Android, owned once for every app.
///
/// The system account chooser (`AccountManager.newChooseAccountIntent`), then
/// `getAuthToken(account, "audience:server:client_id:<web client id>")`. The
/// result is a Google ID token Firebase `signInWithIdp` accepts: one dialog,
/// no browser, no Google client library, no Play Services SDK in the APK.
///
/// Why a plugin: the Kotlin used to be copied into each app, and per-repo
/// OAuth code drifts. Apps depend on this package instead and keep only their
/// own constants (the pinned uid and the Web client id).
///
/// Other platforms (web, Linux desktop, iOS) have no AccountManager.
/// [googleIdToken] returns null there, so the caller falls back to its
/// password path exactly as it does after the user dismisses the chooser.
library;

import 'dart:developer';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// The channel `GoogleAccountTokenPlugin.kt` listens on.
const kGoogleAccountTokenChannel = MethodChannel(
  'dev.kuhy/google_account_token',
);

/// Whether this platform can produce a token at all.
///
/// True only on Android. Use it to hide a "Sign in with Google" button that
/// could never succeed, rather than showing one that always reports
/// "cancelled".
bool get googleAccountTokenSupported =>
    !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

/// A Google ID token for the signed-in account, or null.
///
/// Null rather than throwing for every ordinary outcome: the user dismissed
/// the chooser, the platform is unsupported, [serverClientId] is empty, the
/// native side is not registered, or the token request failed. Failures are
/// logged (level 900) because a configuration error (unregistered SHA-1,
/// wrong client id) arrives through the same path as "the user changed their
/// mind" and is otherwise indistinguishable.
///
/// [serverClientId] must be the project's **Web** OAuth client id. An Android
/// client id yields a token Firebase rejects with `audience mismatch`.
///
/// [accountHint] is an account name (an email) pre-selected in the chooser.
/// The chooser is always shown, so this saves a tap but never skips consent.
Future<String?> googleIdToken({
  required String serverClientId,
  String? accountHint,
}) async {
  if (!googleAccountTokenSupported) return null;
  if (serverClientId.isEmpty) {
    log(
      'Google sign-in unavailable: no server client id; '
      'falling back to the password path',
      level: 900,
    );
    return null;
  }
  try {
    return await kGoogleAccountTokenChannel.invokeMethod<String>('idToken', {
      'serverClientId': serverClientId,
      'accountHint': ?accountHint,
    });
  } on PlatformException catch (error, stackTrace) {
    log(
      'AccountManager token failed',
      level: 900,
      error: error,
      stackTrace: stackTrace,
    );
    return null;
  } on MissingPluginException catch (error, stackTrace) {
    log(
      'google_account_token native side is not registered',
      level: 900,
      error: error,
      stackTrace: stackTrace,
    );
    return null;
  }
}
