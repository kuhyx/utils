import 'package:crdt_sync/crdt_sync.dart';
import 'package:test/test.dart';

Hlc _make(int wallTimeMs, {int counter = 0, String nodeId = 'node-a'}) =>
    Hlc(wallTimeMs: wallTimeMs, counter: counter, nodeId: nodeId);

void main() {
  group('mergeField', () {
    test('greater Hlc wins', () {
      final older = ('a', _make(100));
      final newer = ('b', _make(200));
      expect(mergeField(older, newer), equals(newer));
      expect(mergeField(newer, older), equals(newer));
    });

    test('equal Hlc keeps the first argument', () {
      final clock = _make(100);
      final a = ('a', clock);
      final b = ('a', clock);
      expect(mergeField(a, b), equals(a));
    });
  });

  group('mergeRecord', () {
    test('throws when ids differ', () {
      final a = Record(id: 'a', fields: {});
      final b = Record(id: 'b', fields: {});
      expect(() => mergeRecord(a, b), throwsArgumentError);
    });

    test('merges disjoint fields', () {
      final a = Record(id: 'x', fields: {'text': ('hello', _make(100))});
      final b = Record(id: 'x', fields: {'priority': ('high', _make(50))});
      final merged = mergeRecord(a, b);
      expect(merged.fields, {
        'text': ('hello', _make(100)),
        'priority': ('high', _make(50)),
      });
    });

    test('shared field keeps the later write', () {
      final a = Record(id: 'x', fields: {'text': ('old', _make(100))});
      final b = Record(id: 'x', fields: {'text': ('new', _make(200))});
      final merged = mergeRecord(a, b);
      expect(merged.fields['text'], equals(('new', _make(200))));
    });

    test('delete is sticky against an older non-deleted copy', () {
      final deleted = Record(
        id: 'x',
        fields: {},
        deleted: true,
        deletedHlc: _make(200),
      );
      final stale = Record(
        id: 'x',
        fields: {'text': ('resurrected', _make(100))},
      );
      expect(mergeRecord(deleted, stale).deleted, isTrue);
      expect(mergeRecord(stale, deleted).deleted, isTrue);
    });

    test('neither side deleted stays not deleted', () {
      final a = Record(id: 'x', fields: {});
      final b = Record(id: 'x', fields: {});
      final merged = mergeRecord(a, b);
      expect(merged.deleted, isFalse);
      expect(merged.deletedHlc, isNull);
    });

    test('both sides deleted keeps the later delete clock', () {
      final a = Record(
        id: 'x',
        fields: {},
        deleted: true,
        deletedHlc: _make(100),
      );
      final b = Record(
        id: 'x',
        fields: {},
        deleted: true,
        deletedHlc: _make(200),
      );
      expect(mergeRecord(a, b).deletedHlc, equals(_make(200)));
    });

    test('both deleted but one side missing a clock keeps the other', () {
      final a = Record(id: 'x', fields: {}, deleted: true);
      final b = Record(
        id: 'x',
        fields: {},
        deleted: true,
        deletedHlc: _make(200),
      );
      expect(mergeRecord(a, b).deletedHlc, equals(_make(200)));
      expect(mergeRecord(b, a).deletedHlc, equals(_make(200)));
    });

    test('is commutative', () {
      final recordA = Record(id: 'x', fields: {'text': ('a', _make(100))});
      final recordB = Record(
        id: 'x',
        fields: {'text': ('b', _make(200)), 'extra': ('e', _make(1))},
      );
      expect(
        mergeRecord(recordA, recordB),
        equals(mergeRecord(recordB, recordA)),
      );
    });

    test('is idempotent', () {
      final record = Record(id: 'x', fields: {'text': ('a', _make(100))});
      expect(mergeRecord(record, record), equals(record));
    });
  });

  group('Record JSON round trip', () {
    test('round trips a record with fields', () {
      final record = Record(
        id: 'x',
        fields: {'text': ('hello', _make(100, nodeId: 'pc'))},
      );
      expect(Record.fromJson(record.toJson()), equals(record));
    });

    test('round trips a deleted record', () {
      final record = Record(
        id: 'x',
        fields: {},
        deleted: true,
        deletedHlc: _make(200),
      );
      expect(Record.fromJson(record.toJson()), equals(record));
    });

    test('round trips a record with no delete clock', () {
      final record = Record(id: 'x', fields: {});
      expect(Record.fromJson(record.toJson()), equals(record));
    });
  });
}
