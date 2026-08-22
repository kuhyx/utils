/// Whether the programmatic Google sign-in flow exists on this platform.
///
/// The io half. `google_sign_in` ships federated implementations for android,
/// ios and web only -- there is no `google_sign_in_linux` -- so a real GTK
/// desktop build (lyricanki has one) answers false here and reaches Google
/// through the loopback flow instead.
library;

import 'dart:io';

/// True on the platforms shipping the programmatic plugin flow.
bool get googleSignInSupported => Platform.isAndroid || Platform.isIOS;

/// Whether the loopback sign-in flow can run: it needs a bindable socket and
/// a system browser, which every `dart:io` platform has.
bool get hasLoopbackBrowser => true;
