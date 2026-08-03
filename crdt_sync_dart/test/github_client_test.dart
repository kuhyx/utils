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

  group('putFileText', () {
    test('creates a new file with no sha when none existed', () async {
      final client = _client([
        _response(404),
        _response(200),
      ], putResponse: _response(201));
      await client.putFileText('devices/pc/log.json', '{}', message: 'm');
    });

    test('updates an existing file by including its sha', () async {
      final client = _client([
        _response(200, {'sha': 'abc123'}),
      ], putResponse: _response(200));
      await client.putFileText('devices/pc/log.json', '{}', message: 'm');
    });

    test(
      'throws RepoNotFoundError when checking sha on a missing repo',
      () async {
        final client = _client([_response(404), _response(404)]);
        expect(
          () => client.putFileText('devices/pc/log.json', '{}', message: 'm'),
          throwsA(isA<RepoNotFoundError>()),
        );
      },
    );

    test('throws GitHubSyncError when the sha check itself fails', () async {
      final client = _client([_response(500)]);
      expect(
        () => client.putFileText('devices/pc/log.json', '{}', message: 'm'),
        throwsA(isA<GitHubSyncError>()),
      );
    });

    test('throws GitHubSyncError on a put network exception', () async {
      final client = _client([
        _response(404),
        _response(200),
      ], putError: http.ClientException('offline'));
      expect(
        () => client.putFileText('devices/pc/log.json', '{}', message: 'm'),
        throwsA(isA<GitHubSyncError>()),
      );
    });

    test('throws GitHubSyncError on a put non-2xx response', () async {
      final client = _client([
        _response(404),
        _response(200),
      ], putResponse: _response(422));
      expect(
        () => client.putFileText('devices/pc/log.json', '{}', message: 'm'),
        throwsA(isA<GitHubSyncError>()),
      );
    });
  });

  group('canAccessRepo', () {
    test('is true when the repo endpoint returns 2xx', () async {
      expect(await _client([_response(200)]).canAccessRepo(), isTrue);
    });

    test('is false when the repo is missing (404)', () async {
      expect(await _client([_response(404)]).canAccessRepo(), isFalse);
    });

    test('is false on a network error', () async {
      expect(await _client([_networkError]).canAccessRepo(), isFalse);
    });
  });

  group('canAccessRemote', () {
    // The RemoteStore spelling must behave exactly like the legacy name.
    test('is true when the repo endpoint returns 2xx', () async {
      expect(await _client([_response(200)]).canAccessRemote(), isTrue);
    });

    test('is false when the repo is missing (404)', () async {
      expect(await _client([_response(404)]).canAccessRemote(), isFalse);
    });

    test('is false on a network error', () async {
      expect(await _client([_networkError]).canAccessRemote(), isFalse);
    });
  });

  group('RemoteStore contract', () {
    test('GitHubClient is a RemoteStore', () {
      expect(_client([]), isA<RemoteStore>());
    });

    test('RepoNotFoundError is catchable as either error type', () {
      // Backend-neutral callers catch RemoteNotFoundError; existing GitHub
      // callers catch GitHubSyncError. One exception must satisfy both.
      final error = RepoNotFoundError('gone');
      expect(error, isA<GitHubSyncError>());
      expect(error, isA<RemoteNotFoundError>());
      expect(error, isA<RemoteSyncError>());
    });

    test('errors stringify as their own type', () {
      expect(GitHubSyncError('boom').toString(), 'GitHubSyncError: boom');
      expect(RepoNotFoundError('gone').toString(), 'RepoNotFoundError: gone');
    });
  });

  group('deleteFile', () {
    test('deletes an existing file (resolves its own sha)', () async {
      final client = _client(
        [_response(200, {'sha': 'abc123'})],
        deleteResponse: _response(200),
      );
      await expectLater(client.deleteFile('devices/pc/log.json'), completes);
    });

    test('is a no-op when the file does not exist', () async {
      // sha lookup 404s, repo-exists check 200s -> null sha -> no DELETE sent.
      final client = _client([
        _response(404),
        _response(200),
      ], deleteError: StateError('DELETE must not be called'));
      await expectLater(client.deleteFile('devices/pc/gone.json'), completes);
    });

    test('throws GitHubSyncError on a delete non-2xx response', () async {
      final client = _client(
        [_response(200, {'sha': 'abc123'})],
        deleteResponse: _response(500),
      );
      expect(
        () => client.deleteFile('devices/pc/log.json'),
        throwsA(isA<GitHubSyncError>()),
      );
    });

    test('throws GitHubSyncError on a delete network exception', () async {
      final client = _client(
        [_response(200, {'sha': 'abc123'})],
        deleteError: http.ClientException('offline'),
      );
      expect(
        () => client.deleteFile('devices/pc/log.json'),
        throwsA(isA<GitHubSyncError>()),
      );
    });
  });
}
