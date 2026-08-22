/// Platform gate for the programmatic Google sign-in flow.
///
/// Conditional export because the answer differs per platform *and* because
/// asking the plugin directly is unsafe: `supportsAuthenticate()` throws
/// `UnimplementedError` where no implementation is registered -- an `Error`,
/// not an `Exception`, so it escapes an ordinary catch and would take down
/// the settings screen's `build()`.
library;

export 'google_platform_io.dart'
    if (dart.library.js_interop) 'google_platform_web.dart';
