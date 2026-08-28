import 'package:crdt_sync/crdt_sync.dart';
import 'package:test/test.dart';

Hlc _make(int wallTimeMs, {int counter = 0, String nodeId = 'node-a'}) =>
    Hlc(wallTimeMs: wallTimeMs, counter: counter, nodeId: nodeId);

Record _record({
  String id = 'r1',
  Map<String, Field>? fields,
  bool deleted = false,
  Hlc? deletedHlc,
}) => Record(
  id: id,
  fields: fields ?? {'title': ('hello', _make(100))},
  deleted: deleted,
  deletedHlc: deletedHlc,
);

void main() {
  group('equality', () {
    test('a non-Record is never equal', () {
      // ignore: unrelated_type_equality_checks
      expect(_record() == 'not a record', isFalse);
    });

    test('same id, fields and tombstone are equal', () {
      expect(_record(), equals(_record()));
    });

    test('a differing id is not equal', () {
      expect(_record(), isNot(equals(_record(id: 'r2'))));
    });

    test('a differing tombstone is not equal', () {
      expect(_record(), isNot(equals(_record(deleted: true))));
    });

    test('a differing deletedHlc is not equal', () {
      expect(
        _record(deleted: true, deletedHlc: _make(100)),
        isNot(equals(_record(deleted: true, deletedHlc: _make(200)))),
      );
    });
  });

  group('field comparison', () {
    // _fieldsEqual is the one part of == that cannot short-circuit on a
    // scalar, so each of its exits gets its own case.
    test('a differing field count is not equal', () {
      expect(
        _record(),
        isNot(
          equals(
            _record(
              fields: {'title': ('hello', _make(100)), 'body': ('x', _make(1))},
            ),
          ),
        ),
      );
    });

    test('a differing field value is not equal', () {
      expect(
        _record(),
        isNot(equals(_record(fields: {'title': ('goodbye', _make(100))}))),
      );
    });

    test('a differing field clock is not equal', () {
      expect(
        _record(),
        isNot(equals(_record(fields: {'title': ('hello', _make(200))}))),
      );
    });

    test('a renamed field of the same count is not equal', () {
      expect(
        _record(),
        isNot(equals(_record(fields: {'heading': ('hello', _make(100))}))),
      );
    });

    test('field order does not affect equality', () {
      final a = _record(
        fields: {'a': ('1', _make(100)), 'b': ('2', _make(200))},
      );
      final b = _record(
        fields: {'b': ('2', _make(200)), 'a': ('1', _make(100))},
      );
      expect(a, equals(b));
    });

    test('an empty field map equals another empty one', () {
      expect(_record(fields: {}), equals(_record(fields: {})));
    });
  });

  group('hashCode', () {
    test('equal records hash equally', () {
      expect(_record().hashCode, _record().hashCode);
    });

    test('a differing id changes the hash', () {
      expect(_record().hashCode, isNot(_record(id: 'r2').hashCode));
    });

    test('hashing does not depend on field order', () {
      final a = _record(
        fields: {'a': ('1', _make(100)), 'b': ('2', _make(200))},
      );
      final b = _record(
        fields: {'b': ('2', _make(200)), 'a': ('1', _make(100))},
      );
      expect(a.hashCode, b.hashCode);
    });

    test('records survive a round trip through a Set', () {
      expect({_record(), _record(), _record(id: 'r2')}, hasLength(2));
    });
  });

  group('toString', () {
    test('names every field so a failed expect is readable', () {
      expect(
        _record(fields: {}).toString(),
        'Record(id: r1, fields: {}, deleted: false, deletedHlc: null)',
      );
    });
  });
}
