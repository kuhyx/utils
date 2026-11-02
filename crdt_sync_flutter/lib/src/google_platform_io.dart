/// Whether the programmatic Google sign-in flow exists on this platform.
///
/// The io half. The flow is the `google_account_token` plugin, which wraps the
/// framework AccountManager and therefore exists on Android only. Every other
/// `dart:io` platform (Linux, Windows, macOS) reaches Google through the
/// loopback flow instead.
library;

import 'package:google_account_token/google_account_token.dart';

/// True where the one-tap AccountManager flow exists: Android.
///
/// Asks the plugin rather than `Platform.isAndroid` so the two can never
/// disagree about where a token can be produced.
bool get googleSignInSupported => googleAccountTokenSupported;

/// Whether the loopback sign-in flow can run: it needs a bindable socket and
/// a system browser, which every `dart:io` platform has.
bool get hasLoopbackBrowser => true;
