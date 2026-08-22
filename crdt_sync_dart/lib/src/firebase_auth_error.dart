import 'dart:convert';

import 'remote_store.dart';

/// Raised for an authentication failure the caller must not silently ignore.
///
/// A [RemoteSyncError] so callers that only care about "sync is broken" can
/// catch one type, while a settings screen can single this out to say
/// "your password is wrong" rather than "the network is down".
class FirebaseAuthError extends RemoteSyncError {
  FirebaseAuthError(super.message);
}

/// The human-readable reason buried in an identitytoolkit error body.
///
/// Returns an empty string for a non-JSON body (a proxy error page, say),
/// where the status code is all the detail there is.
String reasonFrom(String body) {
  try {
    final decoded = jsonDecode(body);
    if (decoded is Map<String, dynamic>) {
      final error = decoded['error'];
      if (error is Map<String, dynamic>) return '(${error['message']})';
      if (error is String) return '($error)';
    }
  } on FormatException {
    // Non-JSON body (a proxy error page, say): the status code is all the
    // detail there is.
  }
  return '';
}
