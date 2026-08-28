import 'package:crdt_sync/crdt_sync.dart';
import 'package:test/test.dart';

Hlc _make(int wallTimeMs, {int counter = 0, String nodeId = 'node-a'}) =>
    Hlc(wallTimeMs: wallTimeMs, counter: counter, nodeId: nodeId);

void main() {
  group('comparison operators', () {
    // compareTo is exercised elsewhere; these cover the four operators that
    // wrap it, each of which has its own boundary at "exactly equal".
    test('> is false for equal clocks', () {
      expect(_make(100) > _make(100), isFalse);
    });

    test('>= is true for equal clocks', () {
      expect(_make(100) >= _make(100), isTrue);
    });

    test('>= is true for a greater clock', () {
      expect(_make(200) >= _make(100), isTrue);
    });

    test('>= is false for a lesser clock', () {
      expect(_make(100) >= _make(200), isFalse);
    });

    test('< is false for equal clocks', () {
      expect(_make(100) < _make(100), isFalse);
    });

    test('< is true for a lesser clock', () {
      expect(_make(100) < _make(200), isTrue);
    });

    test('<= is true for equal clocks', () {
      expect(_make(100) <= _make(100), isTrue);
    });

    test('<= is false for a greater clock', () {
      expect(_make(200) <= _make(100), isFalse);
    });
  });

  group('equality', () {
    test('a non-Hlc is never equal', () {
      // ignore: unrelated_type_equality_checks
      expect(_make(100) == 'not an hlc', isFalse);
    });

    test('differing wall time is not equal', () {
      expect(_make(100), isNot(equals(_make(200))));
    });

    test('differing counter is not equal', () {
      expect(_make(100), isNot(equals(_make(100, counter: 1))));
    });

    test('differing node id is not equal', () {
      expect(_make(100), isNot(equals(_make(100, nodeId: 'node-b'))));
    });
  });

  group('hashCode', () {
    test('equal clocks hash equally', () {
      expect(_make(100, counter: 2).hashCode, _make(100, counter: 2).hashCode);
    });

    test('a differing field changes the hash', () {
      expect(
        _make(100, counter: 2).hashCode,
        isNot(_make(100, counter: 3).hashCode),
      );
    });

    test('clocks survive a round trip through a Set', () {
      final set = {_make(100), _make(100), _make(200)};
      expect(set, hasLength(2));
    });
  });

  group('toString', () {
    test('names every field so a failed expect is readable', () {
      expect(
        _make(100, counter: 2, nodeId: 'node-z').toString(),
        'Hlc(wallTimeMs: 100, counter: 2, nodeId: node-z)',
      );
    });
  });
}
