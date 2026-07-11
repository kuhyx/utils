import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:crdt_sync/crdt_sync_io.dart';
import 'package:test/test.dart';

Hlc _make(int wallTimeMs, {int counter = 0, String nodeId = 'node-a'}) =>
    Hlc(wallTimeMs: wallTimeMs, counter: counter, nodeId: nodeId);

Record _rec(String id, String text, Hlc hlc) =>
    Record(id: id, fields: {'text': (text, hlc)});

/// An in-memory [LogPersistence] so the core store is testable without disk.
class _MemoryPersistence implements LogPersistence {
  String? text;
  int writes = 0;

  @override
  Future<String?> read() async => text;

  @override
  Future<void> write(String value) async {
    text = value;
    writes++;
  }
}

void main() {
  group('logToJson / logFromJson', () {
    test('round-trips a log', () {
      final log = <String, Record>{
        'a': _rec('a', 'alpha', _make(100)),
        'b': Record(id: 'b', fields: {}, deleted: true, deletedHlc: _make(200)),
      };
      expect(logFromJson(logToJson(log)), equals(log));
    });

    test('throws FormatException on non-JSON text', () {
      expect(() => logFromJson('{not json'), throwsFormatException);
    });

    test('throws TypeError on valid JSON of the wrong shape', () {
      expect(() => logFromJson('[]'), throwsA(isA<TypeError>()));
    });
  });

  group('LogStore.load', () {
    test('is empty when nothing was ever persisted', () async {
      final store = LogStore(persistence: _MemoryPersistence(), nodeId: 'n');
      expect(await store.load(), isEmpty);
      expect(store.values, isEmpty);
    });

    test('hydrates from a valid stored payload', () async {
      final persistence = _MemoryPersistence()
        ..text = logToJson({'a': _rec('a', 'alpha', _make(100))});
      final store = LogStore(persistence: persistence, nodeId: 'n');
      final log = await store.load();
      expect(log.keys, ['a']);
      expect(store.get('a')!.fields['text']!.$1, 'alpha');
    });

    test('treats a syntactically corrupt payload as empty', () async {
      final persistence = _MemoryPersistence()..text = '{not json';
      final store = LogStore(persistence: persistence, nodeId: 'n');
      expect(await store.load(), isEmpty);
    });

    test('treats a wrong-shape payload as empty', () async {
      final persistence = _MemoryPersistence()..text = '[]';
      final store = LogStore(persistence: persistence, nodeId: 'n');
      expect(await store.load(), isEmpty);
    });
  });

  group('LogStore mutations', () {
    test('upsert stores the record and persists', () async {
      final persistence = _MemoryPersistence();
      final store = LogStore(persistence: persistence, nodeId: 'n');
      await store.load();
      final record = _rec('a', 'alpha', store.nextHlc());
      await store.upsert(record);
      expect(store.get('a'), record);
      expect(persistence.writes, 1);
      expect(logFromJson(persistence.text!)['a'], record);
    });

    test('delete tombstones in place and persists', () async {
      final store = LogStore(persistence: _MemoryPersistence(), nodeId: 'n');
      await store.load();
      await store.upsert(_rec('a', 'alpha', store.nextHlc()));
      await store.delete('a');
      final tombstone = store.get('a')!;
      expect(tombstone.deleted, isTrue);
      expect(tombstone.deletedHlc, isNotNull);
      expect(tombstone.fields['text']!.$1, 'alpha'); // fields retained
    });

    test('delete is a no-op for an absent id', () async {
      final persistence = _MemoryPersistence();
      final store = LogStore(persistence: persistence, nodeId: 'n');
      await store.load();
      await store.delete('missing');
      expect(persistence.writes, 0);
    });

    test('delete is a no-op for an already-tombstoned record', () async {
      final persistence = _MemoryPersistence();
      final store = LogStore(persistence: persistence, nodeId: 'n');
      await store.load();
      await store.upsert(_rec('a', 'alpha', store.nextHlc()));
      await store.delete('a');
      final writesAfterFirstDelete = persistence.writes;
      await store.delete('a');
      expect(persistence.writes, writesAfterFirstDelete);
    });

    test('replaceAll swaps the whole log and persists', () async {
      final persistence = _MemoryPersistence();
      final store = LogStore(persistence: persistence, nodeId: 'n');
      await store.load();
      await store.upsert(_rec('a', 'alpha', store.nextHlc()));
      final merged = <String, Record>{'b': _rec('b', 'beta', _make(500))};
      await store.replaceAll(merged);
      expect(store.values.map((r) => r.id), ['b']);
      expect(logFromJson(persistence.text!), merged);
    });
  });

  group('LogStore clock & snapshot', () {
    test('nextHlc is strictly monotonic', () async {
      final store = LogStore(persistence: _MemoryPersistence(), nodeId: 'n');
      final first = store.nextHlc();
      final second = store.nextHlc();
      expect(second > first, isTrue);
    });

    test('nextHlc stays ahead of hydrated field clocks', () async {
      final far = _make(1 << 40); // a clock far in the future
      final persistence = _MemoryPersistence()
        ..text = logToJson({'a': _rec('a', 'alpha', far)});
      final store = LogStore(persistence: persistence, nodeId: 'n');
      await store.load();
      expect(store.nextHlc() > far, isTrue);
    });

    test('snapshot is unmodifiable', () async {
      final store = LogStore(persistence: _MemoryPersistence(), nodeId: 'n');
      await store.load();
      expect(
        () => store.snapshot()['x'] = _rec('x', 'y', _make(1)),
        throwsUnsupportedError,
      );
    });

    test('get returns null for an absent id', () async {
      final store = LogStore(persistence: _MemoryPersistence(), nodeId: 'n');
      await store.load();
      expect(store.get('nope'), isNull);
    });
  });

  group('LogStore.changes', () {
    test('fires once per mutation', () async {
      final store = LogStore(persistence: _MemoryPersistence(), nodeId: 'n');
      await store.load();
      final events = <void>[];
      final sub = store.changes.listen(events.add);
      await store.upsert(_rec('a', 'alpha', store.nextHlc()));
      await store.delete('a');
      await Future<void>.delayed(Duration.zero);
      expect(events.length, 2);
      await sub.cancel();
    });

    test('close ends the stream and later writes do not throw', () async {
      final persistence = _MemoryPersistence();
      final store = LogStore(persistence: persistence, nodeId: 'n');
      await store.load();
      await store.close();
      // isClosed guard: the write still lands, the (closed) stream is skipped.
      await store.upsert(_rec('a', 'alpha', _make(1)));
      expect(persistence.writes, 1);
    });
  });

  group('FileLogPersistence', () {
    late Directory dir;

    setUp(() async {
      dir = await Directory.systemTemp.createTemp('crdt_sync_store_test');
    });

    tearDown(() async {
      if (dir.existsSync()) await dir.delete(recursive: true);
    });

    test('read returns null when the file does not exist', () async {
      final persistence = FileLogPersistence(File('${dir.path}/nope.json'));
      expect(await persistence.read(), isNull);
    });

    test('write then read round-trips and creates parent dirs', () async {
      final path = '${dir.path}/nested/deep/log.json';
      final persistence = FileLogPersistence(File(path));
      await persistence.write('hello');
      expect(await persistence.read(), 'hello');
      expect(File(path).existsSync(), isTrue);
    });

    test('write overwrites atomically', () async {
      final file = File('${dir.path}/log.json');
      final persistence = FileLogPersistence(file);
      await persistence.write('first');
      await persistence.write('second');
      expect(await persistence.read(), 'second');
    });

    test('backs a LogStore end to end', () async {
      final file = File('${dir.path}/store.json');
      final store = LogStore(
        persistence: FileLogPersistence(file),
        nodeId: 'device-1',
      );
      await store.load();
      await store.upsert(_rec('a', 'alpha', store.nextHlc()));

      final reopened = LogStore(
        persistence: FileLogPersistence(file),
        nodeId: 'device-1',
      );
      final log = await reopened.load();
      expect(log['a']!.fields['text']!.$1, 'alpha');
    });
  });
}
