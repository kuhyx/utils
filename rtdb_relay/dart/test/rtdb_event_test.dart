import 'package:flutter_test/flutter_test.dart';
import 'package:rtdb_relay/src/json_tree.dart';
import 'package:rtdb_relay/src/rtdb_event.dart';

void main() {
  group('SseParser', () {
    test('frames split across chunks, CRLF, comments, multi-line data', () {
      final p = SseParser();
      expect(p.add('event: put\r\ndata: {"path":"/",'), isEmpty);
      final frames = p.add('"data":1}\r\n\r\n: comment\nid: 1\n\n');
      expect(frames, hasLength(1));
      expect(frames.single.event, 'put');
      expect(frames.single.data, '{"path":"/","data":1}');
      final multi = p.add('event: x\ndata: a\ndata:b\n\n');
      expect(multi.single.data, 'a\nb');
    });
  });

  group('RtdbEvent.fromFrame', () {
    test('put and patch', () {
      final put =
          RtdbEvent.fromFrame(
                const SseFrame('put', '{"path":"/a","data":{"x":1}}'),
              )!
              as RtdbPut;
      expect(put.path, '/a');
      expect(put.data, {'x': 1});
      final patch =
          RtdbEvent.fromFrame(
                const SseFrame('patch', '{"path":"/","data":{"b":2}}'),
              )!
              as RtdbPatch;
      expect(patch.data, {'b': 2});
    });

    test('control events and unknown ones', () {
      expect(
        RtdbEvent.fromFrame(const SseFrame('keep-alive', 'null')),
        isA<RtdbKeepAlive>(),
      );
      final cancel = RtdbEvent.fromFrame(const SseFrame('cancel', 'denied'));
      expect((cancel! as RtdbCancel).reason, 'denied');
      expect(
        RtdbEvent.fromFrame(const SseFrame('auth_revoked', 'x')),
        isA<RtdbAuthRevoked>(),
      );
      expect(RtdbEvent.fromFrame(const SseFrame('other', '')), isNull);
    });
  });

  group('json tree', () {
    test('put at root, nested put, delete collapses empty maps', () {
      var t = applyEvent(null, const RtdbPut('/', {'a': 1}));
      t = applyEvent(t, const RtdbPut('/b/c', 2));
      expect(t, {
        'a': 1,
        'b': {'c': 2},
      });
      expect(getAt(t, 'b/c'), 2);
      expect(getAt(t, 'a/x'), isNull);
      t = applyEvent(t, const RtdbPut('/b/c', null));
      expect(t, {'a': 1});
      t = applyEvent(t, const RtdbPut('/a', null));
      expect(t, isNull);
    });

    test('patch replaces each child; others untouched; non-data no-op', () {
      final before = {
        'w': {'x': 1, 'y': 2},
      };
      final after = applyEvent(before, const RtdbPatch('/w', {'x': 9, 'z': 3}));
      expect(after, {
        'w': {'x': 9, 'y': 2, 'z': 3},
      });
      expect(before['w'], {'x': 1, 'y': 2});
      for (final e in const <RtdbEvent>[
        RtdbConnected(),
        RtdbDisconnected(null),
        RtdbKeepAlive(),
        RtdbCancel('r'),
        RtdbAuthRevoked(),
      ]) {
        expect(applyEvent(after, e), same(after));
      }
    });

    test('a put under a scalar replaces it with a map', () {
      expect(setAt(5, 'a', 1), {'a': 1});
    });
  });
}
