import 'package:crdt_sync/crdt_sync.dart';
import 'package:test/test.dart';

Hlc _make(int wallTimeMs, {int counter = 0, String nodeId = 'node-a'}) =>
    Hlc(wallTimeMs: wallTimeMs, counter: counter, nodeId: nodeId);

void main() {
  group('ordering', () {
    test('greater wall time wins', () {
      expect(_make(200) > _make(100), isTrue);
    });

    test('equal wall time, greater counter wins', () {
      expect(_make(100, counter: 2) > _make(100, counter: 1), isTrue);
    });

    test('equal wall time and counter breaks tie on nodeId', () {
      expect(
        _make(100, counter: 1, nodeId: 'b') >
            _make(100, counter: 1, nodeId: 'a'),
        isTrue,
      );
    });

    test('identical clocks compare equal', () {
      expect(
        _make(100, counter: 1, nodeId: 'a'),
        equals(_make(100, counter: 1, nodeId: 'a')),
      );
    });
  });

  group('newTick', () {
    test('first tick has counter zero', () {
      final tick = Hlc.newTick('node-a', wallTimeMsOverride: 1000);
      expect(tick, equals(_make(1000)));
    });

    test('advancing wall clock resets counter', () {
      final previous = _make(1000, counter: 5);
      final tick = Hlc.newTick(
        'node-a',
        previous: previous,
        wallTimeMsOverride: 2000,
      );
      expect(tick, equals(_make(2000)));
    });

    test('stalled wall clock increments counter', () {
      final previous = _make(1000, counter: 5);
      final tick = Hlc.newTick(
        'node-a',
        previous: previous,
        wallTimeMsOverride: 1000,
      );
      expect(tick, equals(_make(1000, counter: 6)));
    });

    test('regressed wall clock still advances monotonically', () {
      final previous = _make(1000, counter: 5);
      final tick = Hlc.newTick(
        'node-a',
        previous: previous,
        wallTimeMsOverride: 500,
      );
      expect(tick, equals(_make(1000, counter: 6)));
    });

    test('defaults to the real clock when unset', () {
      final tick = Hlc.newTick('node-a');
      expect(tick.nodeId, 'node-a');
      expect(tick.wallTimeMs, greaterThan(0));
    });
  });

  group('string round trip', () {
    test('round trips through toStr and fromStr', () {
      final original = _make(1751000123456, counter: 7, nodeId: 'phone');
      expect(Hlc.fromStr(original.toStr()), equals(original));
    });

    test('toStr is lexicographically sortable by wall time', () {
      expect(_make(1000).toStr().compareTo(_make(2000).toStr()), lessThan(0));
    });

    test('toStr is lexicographically sortable by counter', () {
      expect(
        _make(
          1000,
          counter: 1,
        ).toStr().compareTo(_make(1000, counter: 200).toStr()),
        lessThan(0),
      );
    });

    test('fromStr rejects a missing Z separator', () {
      expect(
        () => Hlc.fromStr('not-a-valid-clock-string-at-all'),
        throwsFormatException,
      );
    });

    test('fromStr rejects a wrong-length iso prefix', () {
      expect(
        () => Hlc.fromStr('2026-07-05T12:00:00Z-0000-node-a'),
        throwsFormatException,
      );
    });

    test('fromStr rejects a missing node id separator', () {
      expect(
        () => Hlc.fromStr('2026-07-05T12:00:00.000Z-0000'),
        throwsFormatException,
      );
    });
  });
}
