import 'dart:async';
import 'dart:ui' show ErrorCallback, PlatformDispatcher;

import 'package:crdt_sync_flutter/crdt_sync_flutter.dart';
import 'package:flutter/foundation.dart';
import 'package:material_ui/material_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'app_errors_support.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late DateTime clock;
  late ErrorQueue queue;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    clock = DateTime.utc(2026, 11, 17, 10);
    queue = await ErrorQueue.open(await SharedPreferences.getInstance());
  });

  ErrorReporter reporter() =>
      ErrorReporter(queue, config: config, now: () => clock);

  group('ErrorReporter', () {
    test('records an error with its app frames', () {
      reporter().report(
        'uncaught.flutter',
        StateError('boom'),
        stack: StackTrace.fromString(
          '#0 a (package:flutter/x.dart:1:1)\n'
          '#1 b (dart:async/y.dart:2:2)\n'
          '#2 c (package:flutter/z.dart:3:3)\n'
          '#3 Home.build (package:todo/home.dart:4:4)',
        ),
      );
      final e = queue.entries.single;
      expect(e.kind, 'uncaught.flutter');
      expect(e.error, 'Bad state: boom');
      expect(e.stack, [
        '#0 a (package:flutter/x.dart:1:1)',
        '#1 b (dart:async/y.dart:2:2)',
        '#3 Home.build (package:todo/home.dart:4:4)',
      ]);
    });

    test('drops identical errors inside the window', () {
      final r = reporter();
      for (var i = 0; i < 10; i++) {
        r.report('k', 'same');
      }
      expect(queue.entries, hasLength(1));
      clock = clock.add(ErrorReporter.window);
      r.report('k', 'same');
      expect(queue.entries, hasLength(2));
    });

    test('keeps at most maxPerMinute a minute', () {
      final r = reporter();
      for (var i = 0; i < ErrorReporter.maxPerMinute + 5; i++) {
        r.report('k', 'e$i');
      }
      expect(queue.entries, hasLength(ErrorReporter.maxPerMinute));
      clock = clock.add(const Duration(minutes: 1));
      r.report('k', 'later');
      expect(queue.entries, hasLength(ErrorReporter.maxPerMinute + 1));
    });

    test('never throws on an error whose toString throws', () {
      reporter().report('k', ThrowingToString());
      expect(queue.entries, isEmpty);
    });

    test('stamps the route', () {
      final r = reporter()..route = '/list';
      r.report('k', 'x');
      expect(queue.entries.single.route, '/list');
    });
  });

  group('SlowWaitReporter', () {
    SlowWaitReporter waits() =>
        SlowWaitReporter(queue, now: () => clock, route: () => '/home');

    test('a wait over a second is one perf.slow entry', () {
      final w = waits().begin('list.load');
      clock = clock.add(const Duration(seconds: 2));
      w
        ..end()
        ..end();
      final e = queue.entries.single;
      expect(e.kind, perfSlowKind);
      expect(e.operation, 'list.load');
      expect(e.durationMs, 2000);
      expect(e.route, '/home');
      expect(e.error, 'list.load waited 2000 ms');
      expect(e.still, isFalse);
    });

    test('a wait under a second writes nothing', () {
      final w = waits().begin('quick');
      clock = clock.add(const Duration(milliseconds: 900));
      w.end();
      expect(queue.entries, isEmpty);
    });

    test('a hung wait is written while still going, then at its end', () async {
      final r = SlowWaitReporter(
        queue,
        now: () => clock,
        stillWaiting: const Duration(milliseconds: 5),
      );
      final w = r.begin('hung');
      clock = clock.add(const Duration(seconds: 6));
      await Future<void>.delayed(const Duration(milliseconds: 30));
      w.end();
      expect(queue.entries.map((e) => e.still), [true, false]);
      expect(queue.entries.first.waitId, queue.entries.last.waitId);
    });

    test('caps slow entries per minute', () {
      final r = waits();
      for (var i = 0; i < SlowWaitReporter.maxPerMinute + 3; i++) {
        final w = r.begin('op');
        clock = clock.add(const Duration(milliseconds: 1500));
        w.end();
      }
      expect(queue.entries, hasLength(SlowWaitReporter.maxPerMinute));
    });
  });

  group('ErrorQueue', () {
    test('survives a restart (offline reports are not lost)', () async {
      reporter().report('k', 'offline');
      await queue.saved;
      final again = await ErrorQueue.open(
        await SharedPreferences.getInstance(),
      );
      expect(again.entries.single.error, 'offline');
    });

    test('keeps the newest maxEntries', () {
      final r = ErrorReporter(queue, config: config, now: () => clock);
      for (var i = 0; i < ErrorQueue.maxEntries + 3; i++) {
        clock = clock.add(const Duration(minutes: 1));
        r.report('k', 'e$i');
      }
      expect(queue.entries, hasLength(ErrorQueue.maxEntries));
      expect(queue.entries.last.error, 'e${ErrorQueue.maxEntries + 2}');
    });

    test('a corrupt store opens empty', () async {
      SharedPreferences.setMockInitialValues({ErrorQueue.key: 'not json'});
      final q = await ErrorQueue.open(await SharedPreferences.getInstance());
      expect(q.entries, isEmpty);
    });
  });

  test('config mark uses the package name, else the app', () {
    // ignore: prefer_const_constructors -- a runtime instance for coverage
    final named = AppErrorsConfig(app: 'a-b', repo: 'o/a', package: 'pkg');
    expect(named.mark, 'package:pkg/');
    // ignore: prefer_const_constructors
    expect(AppErrorsConfig(app: 'a-b', repo: 'o/a').mark, 'package:a_b/');
  });

  test('redactForReport masks secrets', () {
    expect(
      redactForReport(
        'GET https://u:p@x.io/a?key=1 Bearer abc eyJa.eyJb.c '
        'password: hunter2 /home/kuhy/file',
      ),
      'GET https://<redacted>@x.io/a?<redacted> Bearer <redacted> <jwt> '
      'password: <redacted> ~/file',
    );
  });

  test('ErrorEntry round-trips through JSON', () {
    final e = ErrorEntry(
      at: DateTime.utc(2026),
      kind: perfSlowKind,
      error: 'x',
      stack: const ['a'],
      route: '/r',
      operation: 'op',
      durationMs: 5,
      waitId: 'w',
      still: true,
    );
    final back = ErrorEntry.fromJson(e.toJson());
    expect(back.toJson(), e.toJson());
    expect(ErrorEntry.tryFromJson('nope'), isNull);
  });
}
