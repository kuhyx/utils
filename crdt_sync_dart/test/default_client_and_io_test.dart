import 'dart:convert';
import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:crdt_sync/crdt_sync_io.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart' as http_testing;
import 'package:test/test.dart';

/// An in-memory [LogPersistence] so store tests need no filesystem.
class _MemoryPersistence implements LogPersistence {
  _MemoryPersistence([this._contents]);

  String? _contents;

  @override
  Future<String?> read() async => _contents;

  @override
  Future<void> write(String contents) async => _contents = contents;
}

void main() {
  group('default http client', () {
    // These constructors fall back to a real http.Client() when none is
    // injected. Nothing here issues a request -- the point is only that the
    // default branch is taken and the resulting client closes cleanly.
    test('GitHubClient builds one when none is injected', () {
      final client = GitHubClient(owner: 'o', repo: 'r', token: 't');
      addTearDown(client.close);
      expect(client.owner, 'o');
      expect(client.repo, 'r');
    });

    test('GitHubClient.close is safe to call', () {
      GitHubClient(owner: 'o', repo: 'r', token: 't').close();
    });

    test('accountFromWrapper builds and closes its own client', () async {
      // Nothing listens on this port, so the GET throws and the `on Exception`
      // path returns null -- while the `finally` still closes the client the
      // function created for itself.
      final account = await accountFromWrapper(
        Uri.parse('http://127.0.0.1:1'),
      );
      expect(account, isNull);
    });

    test('accountFromWrapper leaves an injected client open', () async {
      final mock = http_testing.MockClient(
        (_) async => http.Response(jsonEncode({}), 404),
      );
      expect(await accountFromWrapper(Uri.parse('http://x'), client: mock),
          isNull);
      // Still usable: the function must not close a client it did not create.
      expect((await mock.get(Uri.parse('http://x'))).statusCode, 404);
    });
  });

  group('RemoteNotFoundError', () {
    test('carries its message and is a RemoteSyncError', () {
      final error = RemoteNotFoundError('nothing synced yet');
      expect(error, isA<RemoteSyncError>());
      expect(error.toString(), contains('nothing synced yet'));
    });
  });

  group('LogStore tombstone clock tracking', () {
    test('a loaded tombstone advances the clock past its deletedHlc', () async {
      // deletedHlc is far ahead of any field clock, so the next local write
      // can only outrank it if load() fed the tombstone's clock in too.
      final deletedHlc = Hlc(
        wallTimeMs: DateTime.utc(2030).millisecondsSinceEpoch,
        counter: 7,
        nodeId: 'node-remote',
      );
      final log = {
        'r1': Record(
          id: 'r1',
          fields: {
            'title': ('old', Hlc(wallTimeMs: 1, counter: 0, nodeId: 'node-a')),
          },
          deleted: true,
          deletedHlc: deletedHlc,
        ),
      };
      final store = LogStore(
        persistence: _MemoryPersistence(logToJson(log)),
        nodeId: 'node-a',
      );
      addTearDown(store.close);
      await store.load();

      expect(store.nextHlc() > deletedHlc, isTrue);
    });
  });

  group('FileLogPersistence', () {
    late Directory dir;

    setUp(() => dir = Directory.systemTemp.createTempSync('crdt_sync_test'));
    tearDown(() => dir.deleteSync(recursive: true));

    test('read returns null when the file does not exist', () async {
      final store = FileLogPersistence(File('${dir.path}/absent.json'));
      expect(await store.read(), isNull);
    });

    test('read returns null when the file cannot be read', () async {
      // A mode-000 file still passes existsSync, so the guard does not fire
      // and readAsString throws PathAccessException (a FileSystemException).
      // A directory would NOT work here: File.existsSync() is false for one,
      // so read() would return early down the guard path instead.
      final file = File('${dir.path}/unreadable.json')..writeAsStringSync('{}');
      final chmod = Process.runSync('chmod', ['000', file.path]);
      expect(chmod.exitCode, 0);
      addTearDown(() => Process.runSync('chmod', ['644', file.path]));

      expect(await FileLogPersistence(file).read(), isNull);
    },
        // root ignores the permission bits, so the exception never fires.
        skip: Platform.environment['USER'] == 'root'
            ? 'permission bits do not apply to root'
            : null);

    test('round-trips what it wrote', () async {
      final store = FileLogPersistence(File('${dir.path}/log.json'));
      await store.write('{"hello":"world"}');
      expect(await store.read(), '{"hello":"world"}');
    });
  });
}
