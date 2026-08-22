import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart' as http_testing;
import 'package:test/test.dart';

http.Response _response(int statusCode, [Object? jsonBody]) =>
    http.Response(jsonEncode(jsonBody ?? {}), statusCode);

/// Sentinel meaning "this GET throws a network exception", since a real
/// [http.Response] can't carry an invalid status code.
final _networkError = Object();

/// Builds a client whose GETs return [getResponses] in call order (each
/// either an [http.Response] or [_networkError]), and whose PUT returns
/// [putResponse] (or throws [putError] if network fails).
GitHubClient _client(
  List<Object> getResponses, {
  http.Response? putResponse,
  Object? putError,
  http.Response? deleteResponse,
  Object? deleteError,
}) {
  var getIndex = 0;
  final mock = http_testing.MockClient((request) async {
    if (request.method == 'GET') {
      final response = getResponses[getIndex];
      getIndex++;
      if (identical(response, _networkError)) {
        throw http.ClientException('offline');
      }
      return response as http.Response;
    }
    if (request.method == 'PUT') {
      if (putError != null) throw putError;
      return putResponse!;
    }
    if (request.method == 'DELETE') {
      if (deleteError != null) throw deleteError;
      return deleteResponse!;
    }
    throw UnsupportedError('unexpected method ${request.method}');
  });
  return GitHubClient(
    owner: 'kuhyx',
    repo: 'crdt-sync-demo',
    token: 'fake-token',
    httpClient: mock,
  );
}

void main() {
  group('getFileText', () {
    test('returns decoded content on success', () async {
      final encoded = base64.encode(utf8.encode('hello world'));
      final client = _client([
        _response(200, {'content': encoded}),
      ]);
      expect(await client.getFileText('devices/pc/log.json'), 'hello world');
    });

    test('returns null for an unused path on a real repo', () async {
      final client = _client([_response(404), _response(200)]);
      expect(await client.getFileText('devices/phone/log.json'), isNull);
    });

    test('throws RepoNotFoundError when the repo itself is missing', () async {
      final client = _client([_response(404), _response(404)]);
      expect(
        () => client.getFileText('devices/pc/log.json'),
        throwsA(isA<RepoNotFoundError>()),
      );
    });

    test('throws GitHubSyncError on a non-2xx non-404', () async {
      final client = _client([_response(500)]);
      expect(
        () => client.getFileText('devices/pc/log.json'),
        throwsA(isA<GitHubSyncError>()),
      );
    });

    test('throws GitHubSyncError on a network exception', () async {
      final client = _client([_networkError]);
      expect(
        () => client.getFileText('devices/pc/log.json'),
        throwsA(isA<GitHubSyncError>()),
      );
    });

    test(
      'treats a network error during the repo check as repo missing',
      () async {
        final client = _client([_response(404), _networkError]);
        expect(
          () => client.getFileText('devices/pc/log.json'),
          throwsA(isA<RepoNotFoundError>()),
        );
      },
    );
  });

  group('listDirectory', () {
    test('returns entry names regardless of type', () async {
      final payload = [
        {'name': 'pc', 'type': 'dir'},
        {'name': 'phone', 'type': 'dir'},
        {'not_a_name': 'x'},
      ];
      final client = _client([_response(200, payload)]);
      expect(await client.listDirectory('devices'), ['pc', 'phone']);
    });

    test('returns an empty list when the response is not a list', () async {
      final client = _client([
        _response(200, {'unexpected': 'shape'}),
      ]);
      expect(await client.listDirectory('devices'), isEmpty);
    });

    test('returns an empty list for an unused path on a real repo', () async {
      final client = _client([_response(404), _response(200)]);
      expect(await client.listDirectory('devices'), isEmpty);
    });

    test('throws RepoNotFoundError when the repo itself is missing', () async {
      final client = _client([_response(404), _response(404)]);
      expect(
        () => client.listDirectory('devices'),
        throwsA(isA<RepoNotFoundError>()),
      );
    });

    test('throws GitHubSyncError on a non-2xx non-404', () async {
      final client = _client([_response(500)]);
      expect(
        () => client.listDirectory('devices'),
        throwsA(isA<GitHubSyncError>()),
      );
    });
  });
}
