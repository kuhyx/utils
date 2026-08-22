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
import 'firebase_errors.dart';
import 'firebase_keys.dart';
import 'remote_store.dart';

const _httpUnauthorized = 401;
const _httpForbidden = 403;

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
    return Uri.parse(
      '$_databaseUrl/$encoded.json',
    ).replace(queryParameters: {'auth': await auth.idToken(), ...query});
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
