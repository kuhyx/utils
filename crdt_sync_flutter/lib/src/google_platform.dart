/// Platform gate for the programmatic Google sign-in flow.
///
/// Conditional export because the answer differs per platform: the io half
/// defers to the `google_account_token` plugin (Android only), the web half is
/// a constant false.
library;

export 'google_platform_io.dart'
    if (dart.library.js_interop) 'google_platform_web.dart';
