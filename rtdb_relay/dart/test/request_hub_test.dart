// Every request in flight shares one ranged `requests` listen.
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:rtdb_relay/src/request_hub.dart';
import 'package:rtdb_relay/src/rtdb_event.dart';

import 'support/fake_stream.dart';

const _requests = 'tutor/v1-e2e/requests';
const _a = '01M4RBCX52MMHCK7K73E6KV910';
const _b = '01M4RBCX52MMHCK7K73E6KV911';
const _older = '01M4RBCX52MMHCK7K73E6KV900';

Future<void> _pump() => Future<void>.delayed(Duration.zero);

void main() {
  late FakeStream stream;
  late RequestHub hub;

  setUp(() {
    stream = FakeStream();
    hub = RequestHub(stream, _requests);
  });

  test(
    'two requests, one listen from the older rid; each sees its own',
    () async {
      final a = <Object?>[];
      final b = <Object?>[];
      final subA = hub.watch(_a).listen(a.add);
      expect(hub.inFlight.value, 1);
      expect(stream.openPaths, [_requests]);
      expect(stream.queries[_requests]!['startAt'], '"$_a"');
      final listen = stream.listens[_requests]!
        ..add(const RtdbConnected())
        ..add(const RtdbKeepAlive())
        ..add(
          const RtdbPut('/', {
            _a: {'req': 1},
          }),
        );
      await _pump();
      expect(a, [
        {'req': 1},
      ]);

      // A newer rid is inside the range already: no new listen, and what is
      // known of it is handed over at once.
      stream.emit('$_requests/$_b', const RtdbPut('/req', 2));
      await _pump();
      final subB = hub.watch(_b).listen(b.add);
      await _pump();
      expect(stream.listens[_requests], same(listen));
      expect(stream.peak, 1);
      expect(hub.inFlight.value, 2);
      expect(b, [
        {'req': 2},
      ]);

      // An event for one request does not wake the other.
      stream.emit('$_requests/$_b', const RtdbPut('/claim', 'w'));
      await _pump();
      expect(a, hasLength(1));
      expect(b.last, {'req': 2, 'claim': 'w'});

      // A reconnect's snapshot answers both.
      listen.add(
        const RtdbPut('/', {
          _a: {'req': 1},
        }),
      );
      await _pump();
      expect(a, hasLength(2));
      expect(b.last, isNull);

      await subA.cancel();
      expect(stream.openPaths, [_requests], reason: 'b still follows');
      await subB.cancel();
      expect(stream.openPaths, isEmpty);
      expect(hub.inFlight.value, 0);
    },
  );

  test('an older rid reopens the listen from it', () async {
    final subA = hub.watch(_a).listen((_) {});
    final first = stream.listens[_requests]!;
    final old = <Object?>[];
    final subOld = hub.watch(_older).listen(old.add);
    expect(stream.listens[_requests], isNot(same(first)));
    expect(first.hasListener, isFalse);
    expect(stream.openPaths, [_requests]);
    expect(stream.queries[_requests]!['startAt'], '"$_older"');
    // Not yet heard: nothing handed over.
    final subNone = hub.watch(_b).listen(old.add);
    await _pump();
    expect(old, isEmpty);
    stream.emit('$_requests/$_older', const RtdbPut('/result', 'r'));
    await _pump();
    expect(old, [
      {'result': 'r'},
    ]);
    await subNone.cancel();
    await subOld.cancel();
    await subA.cancel();
    expect(stream.openPaths, isEmpty);
    expect(hub.inFlight.value, 0);
  });

  test('two watchers of the same rid both hear it', () async {
    final got = <Object?>[];
    final one = hub.watch(_a).listen(got.add);
    final two = hub.watch(_a).listen(got.add);
    stream.emit('$_requests/$_a', const RtdbPatch('/', {'claim': 'w'}));
    await _pump();
    expect(got, hasLength(2));
    await one.cancel();
    expect(stream.openPaths, [_requests]);
    unawaited(two.cancel());
  });

  test('the listen ending for good ends every follow', () async {
    var ended = 0;
    hub.watch(_a).listen(null, onDone: () => ended++);
    hub.watch(_b).listen(null, onDone: () => ended++);
    await stream.listens[_requests]!.close();
    await _pump();
    expect(ended, 2);
    expect(hub.inFlight.value, 0);
    expect(stream.openPaths, isEmpty);
    // The next follow opens a fresh listen.
    final sub = hub.watch(_b).listen(null);
    expect(stream.openPaths, [_requests]);
    expect(stream.queries[_requests]!['startAt'], '"$_b"');
    await sub.cancel();
  });
}
