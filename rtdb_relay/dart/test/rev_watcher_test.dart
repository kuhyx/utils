import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:rtdb_relay/src/rev_watcher.dart';
import 'package:rtdb_relay/src/rtdb_client.dart';
import 'package:rtdb_relay/src/rtdb_event.dart';
import 'package:rtdb_relay/src/rtdb_stream.dart';

class _FakeStream implements RtdbStream {
  StreamController<RtdbEvent>? events;
  final paths = <String>[];

  @override
  RtdbClient get client => throw UnimplementedError();

  @override
  Stream<RtdbEvent> listen(
    String path, {
    Map<String, String> query = const {},
  }) {
    paths.add(path);
    return (events = StreamController<RtdbEvent>()).stream;
  }
}

const _rev = 'tutor/v1-e2e/rev';

void main() {
  final binding = TestWidgetsFlutterBinding.ensureInitialized();

  setUp(
    () => binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed),
  );

  test('revOf and foregroundFor', () {
    expect(revOf(null, 'catalog'), 0);
    expect(revOf(const {'stats': 3}, 'catalog'), 0);
    expect(revOf(const {'catalog': 'x'}, 'catalog'), 0);
    expect(revOf(const {'catalog': 7.0}, 'catalog'), 7);
    expect(foregroundFor(null), isTrue);
    expect(foregroundFor(AppLifecycleState.resumed), isTrue);
    expect(foregroundFor(AppLifecycleState.inactive), isNull);
    for (final s in [
      AppLifecycleState.hidden,
      AppLifecycleState.paused,
      AppLifecycleState.detached,
    ]) {
      expect(foregroundFor(s), isFalse);
    }
  });

  test(
    'emits real catalog moves only; reconnect snapshots are ignored',
    () async {
      final s = _FakeStream();
      final w = RevWatcher(s, _rev);
      final seen = <int>[];
      final sub = w.changesOf('catalog').listen(seen.add);
      expect(s.paths, ['tutor/v1-e2e/rev']);
      s.events!
        ..add(const RtdbConnected())
        ..add(const RtdbPut('/', {'catalog': 7, 'stats': 3}))
        ..add(const RtdbPatch('/', {'stats': 4}))
        ..add(const RtdbKeepAlive())
        ..add(const RtdbPut('/catalog', 8))
        // A reconnect resends the whole node, unchanged: not a move.
        ..add(const RtdbDisconnected(null))
        ..add(const RtdbConnected())
        ..add(const RtdbPut('/', {'catalog': 8, 'stats': 4}))
        ..add(const RtdbPatch('/', {'catalog': 9}));
      await pumpEventQueue();
      expect(seen, [8, 9]);
      await sub.cancel();
      await w.dispose();
    },
  );

  test(
    'a key watched late keeps the baseline it had, absent reads 0',
    () async {
      final s = _FakeStream();
      final w = RevWatcher(s, _rev);
      final catalog = w.changesOf('catalog').listen((_) {});
      s.events!.add(const RtdbPut('/', {'catalog': 1}));
      await pumpEventQueue();
      final stats = <int>[];
      final late = w.changesOf('stats').listen(stats.add);
      final todo = <int>[];
      final fresh = w.changesOf('todo').listen(todo.add);
      s.events!
        ..add(const RtdbPatch('/', {'stats': 2}))
        ..add(const RtdbPatch('/', {'catalog': 1}));
      await pumpEventQueue();
      expect(stats, [2]); // 0 -> 2 is a move
      expect(todo, isEmpty);
      await (catalog.cancel(), late.cancel(), fresh.cancel()).wait;
      await w.dispose();
    },
  );

  test(
    'ref-counted: one listen for many screens, closed by the last',
    () async {
      final s = _FakeStream();
      final w = RevWatcher(s, _rev);
      final a = w.changesOf('catalog').listen((_) {});
      final b = w.changesOf('catalog').listen((_) {});
      expect(s.paths, hasLength(1));
      await a.cancel();
      expect(w.listening, isTrue);
      await b.cancel();
      expect(w.listening, isFalse);
      expect(s.events!.hasListener, isFalse);
      // The baseline survives: a move seen on the next listen is emitted.
      final seen = <int>[];
      final c = w.changesOf('catalog').listen(seen.add);
      expect(s.paths, hasLength(2));
      s.events!.add(const RtdbPut('/', {'catalog': 1}));
      await pumpEventQueue();
      expect(seen, isEmpty); // first value ever = baseline
      await c.cancel();
      await w.dispose();
    },
  );

  test(
    'pauses in the back, resumes in front; a missed move is emitted',
    () async {
      final s = _FakeStream();
      // Without listeners, coming to the front opens nothing.
      final w = RevWatcher(s, _rev)..foreground(visible: true);
      expect(s.paths, isEmpty);
      final seen = <int>[];
      final sub = w.changesOf('catalog').listen(seen.add);
      s.events!.add(const RtdbPut('/', {'catalog': 7}));
      await pumpEventQueue();
      final first = s.events!;
      binding
        ..handleAppLifecycleStateChanged(AppLifecycleState.inactive)
        ..handleAppLifecycleStateChanged(AppLifecycleState.hidden);
      await pumpEventQueue();
      expect(w.listening, isFalse);
      expect(first.hasListener, isFalse);
      binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      expect(w.listening, isFalse); // inactive alone decides nothing
      binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      expect(w.listening, isTrue);
      expect(s.paths, hasLength(2));
      s.events!
        ..add(const RtdbConnected())
        ..add(const RtdbPut('/', {'catalog': 9}));
      await pumpEventQueue();
      expect(seen, [9]);
      // `cancel` ends the listen; the next return to the front reopens it.
      await s.events!.close();
      await pumpEventQueue();
      expect(w.listening, isFalse);
      w.foreground(visible: true);
      expect(s.paths, hasLength(3));
      await sub.cancel();
      await w.dispose();
    },
  );

  test('opened while hidden: waits for the front', () async {
    binding
      ..handleAppLifecycleStateChanged(AppLifecycleState.inactive)
      ..handleAppLifecycleStateChanged(AppLifecycleState.hidden);
    final s = _FakeStream();
    final w = RevWatcher(s, _rev, binding: binding);
    final sub = w.changesOf('catalog').listen((_) {});
    expect(s.paths, isEmpty);
    binding
      ..handleAppLifecycleStateChanged(AppLifecycleState.inactive)
      ..handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    expect(s.paths, hasLength(1));
    await w.dispose();
    await sub.cancel();
  });

  test('stats moves: one shared listen for both streams', () async {
    final s = _FakeStream();
    final w = RevWatcher(s, _rev, binding: binding);
    final stats = <int>[];
    final catalog = <int>[];
    final a = w.changesOf('stats').listen(stats.add);
    final b = w.changesOf('catalog').listen(catalog.add);
    expect(s.paths, ['tutor/v1-e2e/rev']); // the second listener shares it
    s.events!
      ..add(const RtdbPut('/', {'catalog': 1, 'stats': 4}))
      ..add(const RtdbPut('/', {'catalog': 1, 'stats': 4}))
      ..add(const RtdbPatch('/', {'stats': 5}));
    await Future<void>.delayed(Duration.zero);
    expect(stats, [5]);
    expect(catalog, isEmpty);
    await b.cancel();
    expect(w.listening, isTrue); // stats still wants it
    await a.cancel();
    expect(w.listening, isFalse);
    await w.dispose();
  });

  test(
    'closed while a request is in flight; a move meanwhile is emitted',
    () async {
      final s = _FakeStream();
      final inFlight = ValueNotifier(0);
      final w = RevWatcher(s, _rev, yieldTo: inFlight);
      final seen = <int>[];
      final sub = w.changesOf('catalog').listen(seen.add);
      s.events!
        ..add(const RtdbConnected())
        ..add(const RtdbPut('/', {'catalog': 3}));
      await Future<void>.delayed(Duration.zero);
      inFlight.value = 1;
      expect(w.listening, isFalse);
      expect(s.events!.hasListener, isFalse);
      inFlight.value = 2; // a second request: still closed, no new listen
      expect(s.paths, hasLength(1));
      // In front again mid-request: stays closed.
      w.foreground(visible: true);
      expect(w.listening, isFalse);
      inFlight.value = 0;
      expect(w.listening, isTrue);
      expect(s.paths, hasLength(2));
      s.events!
        ..add(const RtdbConnected())
        ..add(const RtdbPut('/', {'catalog': 4}));
      await Future<void>.delayed(Duration.zero);
      expect(seen, [4]);
      await sub.cancel();
      await w.dispose();
      inFlight.value = 1; // no longer heard
      expect(s.paths, hasLength(2));
    },
  );
}
