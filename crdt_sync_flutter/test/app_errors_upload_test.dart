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

  test('install reads the default preferences', () async {
    final saved = (FlutterError.onError, PlatformDispatcher.instance.onError);
    final errors = await installAppErrors(config);
    expect(errors.config.mark, 'package:todo/');
    FlutterError.onError = saved.$1;
    PlatformDispatcher.instance.onError = saved.$2;
    AppErrors.instance = null;
  });
}
