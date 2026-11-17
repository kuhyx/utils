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
}
