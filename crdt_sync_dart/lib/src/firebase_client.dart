/// Firebase Realtime Database as dumb keyed storage, over its REST API.
///
/// The RTDB REST endpoints are plain HTTPS, so this works identically on
/// Linux desktop, Android and headless systemd -- unlike `firebase_database`,
/// which has no Linux desktop support at all.
///
/// Why RTDB rather than Firestore: on the Spark (free) plan RTDB bills only
/// storage and bandwidth, with **no per-operation quota**, so a misbehaving
/// sync loop can never exhaust a daily budget and silently stop working
/// mid-day. Its path model is also a direct match for the existing
/// `<pathPrefix>/<deviceId>/<filename>` layout.
library;

import 'dart:convert';

import 'package:http/http.dart' as http;

import 'firebase_auth_rest.dart';
import 'remote_store.dart';

const _httpUnauthorized = 401;
const _httpForbidden = 403;

/// Characters Realtime Database forbids in a key, plus `~` itself because it
/// is this module's escape character.
///
/// `/` is absent deliberately: it is the path separator, so it is handled by
/// splitting into segments before any segment is escaped.
const _escapedChars = {
  '~': '~7E',
  '.': '~2E',
  r'$': '~24',
  '#': '~23',
  '[': '~5B',
  ']': '~5D',
};

/// Raised for a Realtime Database failure the caller must not silently
/// ignore.
class FirebaseSyncError extends RemoteSyncError {
  FirebaseSyncError(super.message);
}

/// Raised when the database itself is unreachable or the credential is not
/// authorized for it.
///
/// The Firebase counterpart of `RepoNotFoundError`: it means "the database
/// URL is wrong, or the security rules reject this uid", as opposed to
/// "nothing has been pushed to that path yet", which is benign and surfaces
/// as a null/empty result.
class DatabaseNotFoundError extends FirebaseSyncError
    implements RemoteNotFoundError {
  DatabaseNotFoundError(super.message);
}

/// Escapes one path segment into a legal Realtime Database key.
///
/// RTDB rejects `. $ # [ ] /` in keys, and the REST API's trailing `.json`
/// is a *format suffix* rather than part of the path -- so a filename like
/// `log.json` cannot be stored verbatim. The mapping is a reversible `~XX`
/// hex escape (`log.json` -> `log~2Ejson`) rather than a lossy "strip the
/// extension", because callers see these names again: todo-app's
/// `listDirectory('todo-sync/notes')` returns *filenames*, not device
/// directories, and must keep getting `<uuid>.json` back.
///
/// `~` is used as the escape character because it is legal in RTDB keys and
/// unreserved in URLs, so the escaped form needs no percent-encoding -- which
/// would otherwise be decoded back into the illegal character by the server.
String encodeKey(String segment) {
  final buffer = StringBuffer();
  for (final rune in segment.split('')) {
    buffer.write(_escapedChars[rune] ?? rune);
  }
  return buffer.toString();
}

/// Reverses [encodeKey].
String decodeKey(String key) {
  final buffer = StringBuffer();
  var index = 0;
  while (index < key.length) {
    final escape = key.length - index >= 3 ? key.substring(index, index + 3) : '';
    final decoded = _escapeToChar[escape];
    if (decoded == null) {
      buffer.write(key[index]);
      index += 1;
    } else {
      buffer.write(decoded);
      index += 3;
    }
  }
  return buffer.toString();
}

final Map<String, String> _escapeToChar = {
  for (final entry in _escapedChars.entries) entry.value: entry.key,
};

/// Escapes every segment of a `/`-separated logical path.
String encodePath(String path) =>
    path.split('/').where((s) => s.isNotEmpty).map(encodeKey).join('/');

/// Realtime Database seen through the same three-method contract as GitHub.
///
/// Reads and writes UTF-8 text blobs stored as JSON string leaves, so the
/// on-the-wire payload is byte-identical to what the GitHub backend stored
/// and the two can be mirrored against each other during migration.
class FirebaseRestClient implements RemoteStore, BulkMapReader {
  FirebaseRestClient({
    required String databaseUrl,
    required this.auth,
    http.Client? httpClient,
  }) : _databaseUrl = databaseUrl.endsWith('/')
           ? databaseUrl.substring(0, databaseUrl.length - 1)
           : databaseUrl,
       _http = httpClient ?? http.Client();

  final String _databaseUrl;

  /// Mints the ID token every request carries. Public so a settings screen
  /// can drive `signIn` / `signOut` through the same instance the client uses.
  final FirebaseTokenProvider auth;
  final http.Client _http;

  Future<Uri> _uri(String path, {Map<String, String> query = const {}}) async {
    final encoded = encodePath(path);
    return Uri.parse('$_databaseUrl/$encoded.json').replace(
      queryParameters: {'auth': await auth.idToken(), ...query},
    );
  }

  /// Turns a non-2xx response into the right error type.
  ///
  /// 401/403 mean the rules rejected this uid or the token is bad -- the
  /// database-level failure a caller may want to single out. Everything else
  /// (including a Spark quota exhaustion, which answers with an error rather
  /// than billing you) is a plain [FirebaseSyncError]. Nothing here is ever
  /// swallowed: a quota-exhausted database that silently returned "no data"
  /// would look exactly like "nothing to sync".
  Never _raise(String what, http.Response res) {
    final detail = res.body.isEmpty ? '' : ' ${res.body.trim()}';
    if (res.statusCode == _httpUnauthorized ||
        res.statusCode == _httpForbidden) {
      throw DatabaseNotFoundError(
        '$what rejected: HTTP ${res.statusCode}$detail -- the database URL '
        'or the security rules do not allow this account',
      );
    }
    throw FirebaseSyncError('$what failed: HTTP ${res.statusCode}$detail');
  }

  Future<http.Response> _get(
    String path, {
    Map<String, String> query = const {},
  }) async {
    try {
      return await _http.get(await _uri(path, query: query));
    } on http.ClientException catch (exc) {
      throw FirebaseSyncError('network error reading $path: $exc');
    }
  }

  @override
  Future<List<String>> listDirectory(String path) async {
    // shallow=true returns `{key: true}` without any values, so listing a
    // directory costs bytes rather than the whole subtree. This is the
    // difference between a sync tick costing hundreds of bytes and costing
    // hundreds of kilobytes.
    final res = await _get(path, query: {'shallow': 'true'});
    if (res.statusCode < 200 || res.statusCode >= 300) {
      _raise('listing $path', res);
    }
    final decoded = jsonDecode(res.body);
    if (decoded is! Map<String, dynamic>) return [];
    return decoded.keys.map(decodeKey).toList();
  }

  @override
  Future<String?> getFileText(String path) async {
    final res = await _get(path);
    if (res.statusCode < 200 || res.statusCode >= 300) {
      _raise('reading $path', res);
    }
    final decoded = jsonDecode(res.body);
    if (decoded == null) return null;
    if (decoded is! String) {
      throw FirebaseSyncError(
        'value at $path is ${decoded.runtimeType}, not the expected text blob',
      );
    }
    return decoded;
  }

  /// Writes [text] at [path]. [message] is ignored -- Realtime Database has
  /// no commit log to attach a reason to.
  @override
  Future<void> putFileText(
    String path,
    String text, {
    required String message,
  }) async {
    late final http.Response res;
    try {
      res = await _http.put(await _uri(path), body: jsonEncode(text));
    } on http.ClientException catch (exc) {
      throw FirebaseSyncError('network error writing $path: $exc');
    }
    if (res.statusCode < 200 || res.statusCode >= 300) {
      _raise('writing $path', res);
    }
  }

  /// Merges [values] into the map at [path], leaving sibling keys alone.
  ///
  /// Used for the shared `revs` map, where a plain PUT would replace the
  /// whole map and wipe every *other* device's entry -- after which those
  /// devices would look permanently unchanged and never be fetched again.
  Future<void> patchValues(String path, Map<String, Object?> values) async {
    late final http.Response res;
    try {
      res = await _http.patch(await _uri(path), body: jsonEncode(values));
    } on http.ClientException catch (exc) {
      throw FirebaseSyncError('network error patching $path: $exc');
    }
    if (res.statusCode < 200 || res.statusCode >= 300) {
      _raise('patching $path', res);
    }
  }

  /// Reads the map at [path] as `key -> string`, or an empty map if absent.
  ///
  /// Tolerates a non-map or malformed value rather than throwing: this backs
  /// the revision cache, which is an *optimisation*. A corrupt revs node must
  /// degrade into "fetch everything", never into a failed sync.
  @override
  Future<Map<String, String>> getStringMap(String path) async {
    final res = await _get(path);
    if (res.statusCode < 200 || res.statusCode >= 300) {
      _raise('reading $path', res);
    }
    final decoded = jsonDecode(res.body);
    if (decoded is! Map<String, dynamic>) return {};
    return {
      for (final entry in decoded.entries)
        if (entry.value is String) decodeKey(entry.key): entry.value as String,
    };
  }

  @override
  Future<void> deleteFile(
    String path, {
    String message = 'crdt_sync: delete',
  }) async {
    late final http.Response res;
    try {
      res = await _http.delete(await _uri(path));
    } on http.ClientException catch (exc) {
      throw FirebaseSyncError('network error deleting $path: $exc');
    }
    if (res.statusCode < 200 || res.statusCode >= 300) {
      _raise('deleting $path', res);
    }
  }

  /// Probes the database root. Never throws -- a bad URL, a rejected token or
  /// a network failure all report false.
  @override
  Future<bool> canAccessRemote() async {
    try {
      final res = await _http.get(await _uri('', query: {'shallow': 'true'}));
      return res.statusCode >= 200 && res.statusCode < 300;
    } on http.ClientException {
      return false;
    } on RemoteSyncError {
      // Includes FirebaseAuthError from the token refresh: "cannot get a
      // token" is exactly "cannot access the remote".
      return false;
    }
  }

  @override
  void close() => _http.close();
}
