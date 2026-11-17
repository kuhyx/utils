/// An in-memory RTDB REST server behind a MockClient: GET (shallow,
/// `orderBy="$key"` + `startAt`), PUT (resolving `.sv` timestamps), PATCH,
/// DELETE. Enough for the logic tests; streaming is faked separately.
library;

import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:rtdb_relay/src/json_tree.dart';
import 'package:rtdb_relay/src/rtdb_client.dart';

import 'tutor_layout.dart';

/// The fake database.
class FakeRtdb {
  /// The whole tree.
  Object? root;

  /// Server time used for `{".sv":"timestamp"}`.
  int serverTime = 1791731346000;

  /// Requests seen, as `METHOD path`.
  final List<String> log = [];

  /// When set, every request throws a network error.
  bool offline = false;

  /// Requests whose path starts with this throw a network error.
  String? failPrefix;

  /// A client wired to this fake.
  ///
  /// The namespace is pinned to production (''): a phone slot build of the
  /// screenshot fixture sets SYNC_NAMESPACE=sandbox/slotN, which would
  /// otherwise move every read under a prefix this in-memory tree lacks
  /// (Home and Progress came up empty on the Pixel).
  RtdbClient client() => RtdbClient(
    layout: tutorLayout,
    databaseUrl: 'https://fake',
    idToken: () async => 'tok',
    httpClient: MockClient(_handle),
    namespace: '',
  );

  Object? _resolve(Object? v) {
    if (v is Map<String, dynamic>) {
      if (v.length == 1 && v['.sv'] == 'timestamp') return serverTime;
      return {for (final e in v.entries) e.key: _resolve(e.value)};
    }
    return v;
  }

  Future<http.Response> _handle(http.Request req) async {
    if (offline) throw http.ClientException('offline');
    final path = req.url.path.replaceFirst(RegExp(r'\.json$'), '');
    if (failPrefix != null && path.startsWith(failPrefix!)) {
      throw http.ClientException('unreachable');
    }
    log.add('${req.method} $path');
    final q = req.url.queryParameters;
    switch (req.method) {
      case 'GET':
        var value = getAt(root, path);
        if (q['shallow'] == 'true' && value is Map<String, dynamic>) {
          value = {for (final k in value.keys) k: true};
        }
        final start = q['startAt'];
        if (start != null && value is Map<String, dynamic>) {
          final from = jsonDecode(start) as String;
          value = {
            for (final e in value.entries)
              if (e.key.compareTo(from) >= 0) e.key: e.value,
          };
          if (value.isEmpty) value = null;
        }
        return http.Response(jsonEncode(value), 200);
      case 'PUT':
        final value = _resolve(jsonDecode(req.body));
        root = setAt(root, path, value);
        return http.Response(jsonEncode(value), 200);
      case 'PATCH':
        final patch = jsonDecode(req.body) as Map<String, dynamic>;
        for (final e in patch.entries) {
          root = setAt(root, '$path/${e.key}', _resolve(e.value));
        }
        return http.Response(req.body, 200);
      default: // DELETE
        root = setAt(root, path, null);
        return http.Response('null', 200);
    }
  }
}
