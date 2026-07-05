import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart' as http_testing;
import 'package:test/test.dart';

Hlc _make(int wallTimeMs, {int counter = 0, String nodeId = 'node-a'}) =>
    Hlc(wallTimeMs: wallTimeMs, counter: counter, nodeId: nodeId);

String _encode(Log log) =>
    jsonEncode(log.map((id, record) => MapEntry(id, record.toJson())));

Log _decode(String text) => (jsonDecode(text) as Map<String, dynamic>).map(
  (id, data) => MapEntry(id, Record.fromJson(data as Map<String, dynamic>)),
);

http.Response _response(int statusCode, [Object? jsonBody]) =>
    http.Response(jsonEncode(jsonBody ?? {}), statusCode);

class _PutCall {
  _PutCall(this.path, this.body);
  final String path;
  final Map<String, dynamic> body;
}

/// Builds a [GitHubClient] backed by an in-memory router: GET
/// `.../contents/<key>` returns `contentResponses[key]` (404 if absent), the
/// bare repo-existence GET always succeeds, and every PUT is recorded into
/// [putCalls] and answered with 200.
({GitHubClient client, List<_PutCall> putCalls}) _client({
  Map<String, http.Response> contentResponses = const {},
}) {
  final putCalls = <_PutCall>[];
  final mock = http_testing.MockClient((request) async {
    final path = request.url.path;
    if (!path.contains('/contents/')) {
      return _response(200);
    }
    final key = path.split('/contents/').last;
    if (request.method == 'PUT') {
      putCalls.add(
        _PutCall(key, jsonDecode(request.body) as Map<String, dynamic>),
      );
      return _response(200);
    }
    return contentResponses[key] ?? _response(404);
  });
  final client = GitHubClient(
    owner: 'kuhyx',
    repo: 'crdt-sync-demo',
    token: 'fake-token',
    httpClient: mock,
  );
  return (client: client, putCalls: putCalls);
}

http.Response _directoryOf(List<String> deviceIds) =>
    _response(200, deviceIds.map((id) => {'name': id, 'type': 'dir'}).toList());

http.Response _fileContaining(String text) =>
    _response(200, {'content': base64.encode(utf8.encode(text))});

void main() {
  group('syncLog', () {
    test('pushes the local log when no other devices have synced', () async {
      final localLog = <String, Record>{
        'a': Record(id: 'a', fields: {'text': ('hello', _make(100))}),
      };
      final (:client, :putCalls) = _client(
        contentResponses: {'devices': _directoryOf([])},
      );

      final merged = await syncLog(
        client: client,
        deviceId: 'pc',
        pathPrefix: 'devices',
        localLog: localLog,
        encode: _encode,
        decode: _decode,
      );

      expect(merged, equals(localLog));
      expect(putCalls, hasLength(1));
      expect(putCalls.single.path, 'devices/pc/log.json');
    });

    test('skips its own device id when listing', () async {
      final (:client, :putCalls) = _client(
        contentResponses: {
          'devices': _directoryOf(['pc', 'phone']),
          'devices/phone/log.json': _fileContaining('{}'),
        },
      );

      await syncLog(
        client: client,
        deviceId: 'pc',
        pathPrefix: 'devices',
        localLog: {},
        encode: _encode,
        decode: _decode,
      );

      expect(putCalls, hasLength(1));
    });

    test('skips a device with no pushed file yet', () async {
      final (:client, :putCalls) = _client(
        contentResponses: {
          'devices': _directoryOf(['phone']),
        },
      );

      final merged = await syncLog(
        client: client,
        deviceId: 'pc',
        pathPrefix: 'devices',
        localLog: {},
        encode: _encode,
        decode: _decode,
      );

      expect(merged, isEmpty);
      expect(putCalls.single.body['content'], base64.encode(utf8.encode('{}')));
    });

    test('skips a device whose pushed file is corrupt', () async {
      final (:client, :putCalls) = _client(
        contentResponses: {
          'devices': _directoryOf(['phone']),
          'devices/phone/log.json': _fileContaining('{not valid json'),
        },
      );

      final merged = await syncLog(
        client: client,
        deviceId: 'pc',
        pathPrefix: 'devices',
        localLog: {},
        encode: _encode,
        decode: _decode,
      );

      expect(merged, isEmpty);
      expect(putCalls, hasLength(1));
    });

    test('merges in a remote device\'s entries', () async {
      final remoteLog = <String, Record>{
        'b': Record(id: 'b', fields: {'text': ('from phone', _make(100))}),
      };
      final (:client, :putCalls) = _client(
        contentResponses: {
          'devices': _directoryOf(['phone']),
          'devices/phone/log.json': _fileContaining(_encode(remoteLog)),
        },
      );

      final merged = await syncLog(
        client: client,
        deviceId: 'pc',
        pathPrefix: 'devices',
        localLog: {},
        encode: _encode,
        decode: _decode,
      );

      expect(merged, equals(remoteLog));
    });

    test('uses a custom filename and commit message', () async {
      final (:client, :putCalls) = _client(
        contentResponses: {'devices': _directoryOf([])},
      );

      await syncLog(
        client: client,
        deviceId: 'pc',
        pathPrefix: 'devices',
        localLog: {},
        encode: _encode,
        decode: _decode,
        filename: 'notes.json',
        commitMessage: 'custom message',
      );

      expect(putCalls.single.path, 'devices/pc/notes.json');
      expect(putCalls.single.body['message'], 'custom message');
    });
  });
}
