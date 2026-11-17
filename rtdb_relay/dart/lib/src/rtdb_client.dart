/// Firebase Realtime Database over REST, with ETag conditional writes.
///
/// crdt_sync's `FirebaseRestClient` stores only string leaves, so the relay
/// keeps its own GET/PUT/PATCH/DELETE. Every request carries
/// `?auth=<idToken>`; the token source refreshes it.
///
/// Under the layout's e2e root (e.g. `tutor/v1-e2e`) every value passes
/// through `sealer` (sealed on write, opened on read). With `sealRequired`
/// (the app) a call there before the key is unlocked throws instead of
/// sending plaintext.
library;

import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart'
    show checkSyncNamespace, syncNamespace;
import 'package:http/http.dart' as http;
import 'package:rtdb_relay/src/layout.dart';
import 'package:rtdb_relay/src/rtdb_types.dart';
import 'package:rtdb_relay/src/sealer.dart';

export 'package:rtdb_relay/src/rtdb_types.dart';

/// The REST client.
class RtdbClient {
  /// Creates a client for [databaseUrl] authenticated by [idToken].
  ///
  /// [namespace] (default: the `SYNC_NAMESPACE` dart-define, as in crdt_sync)
  /// is empty for production or `sandbox/<slot>`; every request path then
  /// lives under `/<namespace>/`. Anything else throws (fail closed).
  new({
    required this.layout,
    required String databaseUrl,
    required this.idToken,
    http.Client? httpClient,
    String? namespace,
    this.sealer,
    this.sealRequired = false,
  }) : _namespace = checkSyncNamespace(namespace ?? syncNamespace),
       _base = databaseUrl.endsWith('/')
           ? databaseUrl.substring(0, databaseUrl.length - 1)
           : databaseUrl,
       _http = httpClient ?? http.Client();

  /// The app's sealed tree.
  final RelayLayout layout;

  final String _base;
  final String _namespace;

  /// Token source; also used by the stream for reconnects.
  final IdTokenSource idToken;
  final http.Client _http;

  /// The underlying HTTP client, shared with the SSE stream.
  http.Client get httpClient => _http;

  /// Seals and opens the e2e root; null until the key is unlocked.
  RelaySealer? sealer;

  /// When true, a call under the e2e root without [sealer] throws.
  final bool sealRequired;

  /// [path] relative to the e2e root, or null when outside it.
  String? e2eRel(String path) => layout.rel(path);

  RelaySealer? _sealerFor(String? rel) {
    if (rel == null) return null;
    if (sealer == null && sealRequired) {
      throw const RtdbError('e2e locked: no key, nothing is sent');
    }
    return sealer;
  }

  /// [value] read at [path] with its sealed units opened.
  Future<Object?> opened(String path, Object? value) async {
    final rel = e2eRel(path);
    final s = _sealerFor(rel);
    return s == null ? value : await s.open(rel!, value);
  }

  Future<Object?> _sealed(String path, Object? value) async {
    final rel = e2eRel(path);
    final s = _sealerFor(rel);
    return s == null ? value : await s.seal(rel!, value);
  }

  /// The REST URL of [path] with a fresh token and [query].
  Future<Uri> uri(String path, {Map<String, String> query = const {}}) async {
    final segments = [
      ..._namespace.split('/'),
      ...path.split('/'),
    ].where((s) => s.isNotEmpty);
    final encoded = segments.map(Uri.encodeComponent).join('/');
    return Uri.parse('$_base/$encoded.json')
        .replace(queryParameters: {'auth': await idToken(), ...query});
  }

  /// Reads [path]; null when absent.
  Future<Object?> get(
    String path, {
    Map<String, String> query = const {},
  }) async {
    final rel = e2eRel(path);
    final unit = rel != null && _sealerFor(rel) != null
        ? layout.unitPath(rel)
        : null;
    if (unit != null) {
      // Below a sealed unit: read the whole unit, open it, walk down.
      var node = await get('${layout.root}/$unit');
      for (final part in e2eParts(rel!).skip(e2eParts(unit).length)) {
        node = node is Map ? node[part] : null;
      }
      return node;
    }
    final res = await _send('GET', path, query: query);
    return await opened(path, _decode(res));
  }

  /// Keys directly under [path] (`shallow=true`, values not transferred).
  Future<List<String>> keys(String path) async {
    final value = await get(path, query: {'shallow': 'true'});
    if (value is! Map) return const [];
    return value.keys.cast<String>().toList()..sort();
  }

  /// Reads [path] with its ETag, for a following conditional write.
  Future<Tagged> getTagged(String path) async {
    final res = await _send('GET', path, headers: {'X-Firebase-ETag': 'true'});
    return Tagged(await opened(path, _decode(res)), res.headers['etag'] ?? '');
  }

  /// Writes [value] at [path]; returns the stored value with server values
  /// (`{".sv":"timestamp"}`) resolved.
  Future<Object?> put(String path, Object? value) async => await opened(
    path,
    _decode(await _send('PUT', path, body: await _sealed(path, value))),
  );

  /// PUT only if the node still has [etag]; a 412 is a lost race.
  Future<ConditionalResult> putIfMatch(
    String path,
    Object? value,
    String etag,
  ) async =>
      await _conditional('PUT', path, etag, body: await _sealed(path, value));

  /// DELETE only if the node still has [etag].
  Future<ConditionalResult> deleteIfMatch(String path, String etag) =>
      _conditional('DELETE', path, etag);

  /// Merges [values] into the map at [path] (no ETag support in RTDB).
  Future<void> patch(String path, Map<String, Object?> values) async {
    final rel = e2eRel(path);
    final s = _sealerFor(rel);
    final body = s == null ? values : await s.sealPatch(rel!, values);
    await _send('PATCH', path, body: body);
  }

  /// Removes [path].
  Future<void> delete(String path) async {
    _sealerFor(e2eRel(path));
    await _send('DELETE', path);
  }

  /// Releases the HTTP client.
  void close() => _http.close();

  Future<ConditionalResult> _conditional(
    String method,
    String path,
    String etag, {
    Object? body,
  }) async {
    final res = await _send(
      method,
      path,
      body: body,
      headers: {'if-match': etag},
      accept412: true,
    );
    return ConditionalResult(
      ok: res.statusCode != 412,
      value: await opened(path, _decode(res)),
      etag: res.headers['etag'],
    );
  }

  Future<http.Response> _send(
    String method,
    String path, {
    Object? body,
    Map<String, String> query = const {},
    Map<String, String> headers = const {},
    bool accept412 = false,
  }) async {
    final request = http.Request(method, await uri(path, query: query))
      ..headers.addAll(headers);
    if (method == 'PUT' || method == 'PATCH') {
      request.body = jsonEncode(body);
    }
    final http.Response res;
    try {
      res = await http.Response.fromStream(await _http.send(request));
    } on http.ClientException catch (exc) {
      throw RtdbError('network error: $method $path: $exc');
    }
    final ok = res.statusCode >= 200 && res.statusCode < 300;
    if (!ok && !(accept412 && res.statusCode == 412)) {
      throw RtdbError(
        '$method $path: HTTP ${res.statusCode} ${res.body.trim()}',
        status: res.statusCode,
      );
    }
    return res;
  }

  static Object? _decode(http.Response res) =>
      res.body.isEmpty ? null : jsonDecode(res.body);
}
