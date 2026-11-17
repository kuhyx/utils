import 'dart:async';
import 'dart:ui' show ErrorCallback, PlatformDispatcher;

import 'package:crdt_sync_flutter/crdt_sync_flutter.dart';
import 'package:flutter/foundation.dart';
import 'package:material_ui/material_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// A sink recording every patch; [fail] makes the next ones throw.
class FakeSink {
  final patches = <String, Map<String, Object?>>{};
  bool fail = false;

  Future<void> call(String path, Map<String, Object?> values) async {
    if (fail) throw StateError('offline');
    (patches[path] ??= {}).addAll(values);
  }

  List<Map<String, Object?>> get entries => [
    for (final v in patches.values.expand((m) => m.values))
      v! as Map<String, Object?>,
  ];
}

const config = AppErrorsConfig(
  app: 'todo',
  repo: 'kuhyx/todo',
  build: 42,
  version: '1.2.3',
);

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
      reporter().report('k', _Throws());
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

  group('ErrorUploader', () {
    test('uploads to /<app>/errors/<device>/<id> with the build', () async {
      final sink = FakeSink();
      reporter().report('k', 'Bad state: token=abc123 me@x.org');
      final up = ErrorUploader(
        queue,
        config: config,
        sink: () async => sink.call,
        deviceId: () async => 'dev-1',
      );
      expect(await up.flush(), isTrue);
      expect(sink.patches.keys.single, 'todo/errors');
      final key = sink.patches['todo/errors']!.keys.single;
      expect(key, startsWith('dev-1/'));
      final e = sink.entries.single;
      expect(e['build'], 42);
      expect(e['version'], '1.2.3');
      expect(e['repo'], 'kuhyx/todo');
      expect(e['mark'], 'package:todo/');
      expect(e['error'], 'Bad state: token=<redacted> <email>');
      expect(queue.entries, isEmpty);
    });

    test('offline keeps the queue; back online sends it', () async {
      final sink = FakeSink()..fail = true;
      reporter().report('k', 'x');
      final up = ErrorUploader(
        queue,
        config: config,
        sink: () async => sink.call,
        deviceId: () async => 'd',
      );
      expect(await up.flush(), isFalse);
      expect(queue.entries, hasLength(1));
      sink.fail = false;
      expect(await up.flush(), isTrue);
      expect(sink.entries, hasLength(1));
      up.dispose();
    });

    test('signed out (no sink) keeps the queue', () async {
      reporter().report('k', 'x');
      final up = ErrorUploader(
        queue,
        config: config,
        sink: () async => null,
        deviceId: () async => 'd',
      );
      expect(await up.flush(), isFalse);
      expect(queue.entries, hasLength(1));
      up.dispose();
    });

    test('nothing pending is a no-op', () async {
      final up = ErrorUploader(
        queue,
        config: config,
        sink: () async => throw StateError('never called'),
        deviceId: () async => 'd',
      );
      expect(await up.flush(), isTrue);
    });

    test('an append schedules a debounced flush', () async {
      final sink = FakeSink();
      final up = ErrorUploader(
        queue,
        config: config,
        sink: () async => sink.call,
        deviceId: () async => 'd',
        debounce: Duration.zero,
      )..start();
      reporter().report('k', 'x');
      await Future<void>.delayed(const Duration(milliseconds: 20));
      expect(sink.entries, hasLength(1));
      up.dispose();
    });
  });

  group('installAppErrors', () {
    late FlutterExceptionHandler? savedFlutter;
    late ErrorCallback? savedAsync;

    setUp(() {
      savedFlutter = FlutterError.onError;
      savedAsync = PlatformDispatcher.instance.onError;
    });

    tearDown(() {
      FlutterError.onError = savedFlutter;
      PlatformDispatcher.instance.onError = savedAsync;
      AppErrors.instance = null;
    });

    test('chains the framework and async hooks', () async {
      final seen = <Object>[];
      FlutterError.onError = (d) => seen.add(d.exception);
      PlatformDispatcher.instance.onError = (e, s) {
        seen.add(e);
        return true;
      };
      final errors = await installAppErrors(
        config,
        preferences: await SharedPreferences.getInstance(),
      );
      expect(AppErrors.instance, same(errors));
      FlutterError.onError!(
        FlutterErrorDetails(exception: StateError('framework')),
      );
      FlutterError.onError!(
        FlutterErrorDetails(exception: StateError('quiet'), silent: true),
      );
      expect(
        PlatformDispatcher.instance.onError!(
          StateError('async'),
          StackTrace.empty,
        ),
        isTrue,
      );
      expect(seen, hasLength(3));
      expect(errors.queue.entries.map((e) => e.kind), [
        'uncaught.flutter',
        'uncaught.async',
      ]);
    });

    test('without prior hooks the async error is not handled', () async {
      FlutterError.onError = null;
      PlatformDispatcher.instance.onError = null;
      final errors = await installAppErrors(
        config,
        preferences: await SharedPreferences.getInstance(),
      );
      FlutterError.onError!(FlutterErrorDetails(exception: StateError('f')));
      expect(
        PlatformDispatcher.instance.onError!('a', StackTrace.empty),
        isFalse,
      );
      expect(errors.queue.entries, hasLength(2));
    });

    test('connect starts uploads; the route observer stamps routes', () async {
      final errors = await installAppErrors(
        config,
        preferences: await SharedPreferences.getInstance(),
      );
      final sink = FakeSink();
      final up = errors.connect(
        sink: () async => sink.call,
        deviceId: () async => 'd',
        startDelay: Duration.zero,
      );
      AppErrorsRouteObserver(errors).didPush(
        MaterialPageRoute<void>(
          builder: (_) => const SizedBox(),
          settings: const RouteSettings(name: '/settings'),
        ),
        null,
      );
      errors.reporter.report('k', 'x');
      await Future<void>.delayed(const Duration(milliseconds: 20));
      await up.flush();
      expect(sink.entries.single['route'], '/settings');
      up.dispose();
    });
  });

  group('WaitWatch', () {
    tearDown(() => AppErrors.instance = null);

    testWidgets('without AppErrors it only shows the child', (tester) async {
      await tester.pumpWidget(const WaitWatch.centered('x'));
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('a spinner shown 2 s is a perf.slow entry', (tester) async {
      var now = DateTime.utc(2026);
      final errors = AppErrors.forTest(config, queue, now: () => now);
      AppErrors.instance = errors;
      await tester.pumpWidget(
        const WaitWatch(operation: 'list.load', child: SizedBox()),
      );
      now = now.add(const Duration(seconds: 2));
      await tester.pumpWidget(const SizedBox());
      expect(queue.entries.single.operation, 'list.load');
    });

    testWidgets('backgrounding ends the wait, resuming starts one', (
      tester,
    ) async {
      var now = DateTime.utc(2026);
      final errors = AppErrors.forTest(config, queue, now: () => now);
      AppErrors.instance = errors;
      await tester.pumpWidget(
        const WaitWatch(operation: 'op', child: SizedBox()),
      );
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      now = now.add(const Duration(seconds: 30));
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      now = now.add(const Duration(milliseconds: 100));
      await tester.pumpWidget(const SizedBox());
      expect(queue.entries, isEmpty, reason: 'background time is no wait');
    });
  });

  test('install reads the default preferences', () async {
    final saved = (FlutterError.onError, PlatformDispatcher.instance.onError);
    final errors = await installAppErrors(config);
    expect(errors.config.mark, 'package:todo/');
    FlutterError.onError = saved.$1;
    PlatformDispatcher.instance.onError = saved.$2;
    AppErrors.instance = null;
  });

  test('config mark uses the package name, else the app', () {
    // ignore: prefer_const_constructors -- a runtime instance for coverage
    final named = AppErrorsConfig(app: 'a-b', repo: 'o/a', package: 'pkg');
    expect(named.mark, 'package:pkg/');
    // ignore: prefer_const_constructors
    expect(AppErrorsConfig(app: 'a-b', repo: 'o/a').mark, 'package:a_b/');
  });

  test('route observer follows pop and replace', () {
    final errors = AppErrors.forTest(config, queue);
    final observer = AppErrorsRouteObserver(errors);
    Route<void> named(String name) => MaterialPageRoute<void>(
      builder: (_) => const SizedBox(),
      settings: RouteSettings(name: name),
    );
    observer.didPop(named('/b'), named('/a'));
    expect(errors.reporter.route, '/a');
    observer.didReplace(newRoute: named('/c'));
    expect(errors.reporter.route, '/c');
    observer.didPop(named('/c'), null);
    expect(errors.reporter.route, '/c', reason: 'no name keeps the last');
  });

  testWidgets('WaitWatch built at runtime', (tester) async {
    // ignore: prefer_const_constructors
    await tester.pumpWidget(WaitWatch.centered('x'));
    // ignore: prefer_const_constructors
    await tester.pumpWidget(WaitWatch(operation: 'y', child: SizedBox()));
    expect(find.byType(SizedBox), findsOneWidget);
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

class _Throws {
  @override
  String toString() => throw StateError('no');
}
