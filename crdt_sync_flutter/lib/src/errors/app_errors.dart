/// App-wide error and slow-wait reporting, in one call (generalised from
/// kartka's `error_hooks.dart`): the PC's `app-errors` ingest turns every
/// report into a self-fixing ticket on kuhy's board.
library;

import 'dart:async';

import 'package:crdt_sync_flutter/src/errors/app_errors_config.dart';
import 'package:crdt_sync_flutter/src/errors/error_queue.dart';
import 'package:crdt_sync_flutter/src/errors/error_reporter.dart';
import 'package:crdt_sync_flutter/src/errors/error_upload.dart';
import 'package:crdt_sync_flutter/src/errors/slow_wait.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// The installed reporting: [reporter] for errors, [waits] for slow waits,
/// both into [queue], which [connect] uploads.
class AppErrors {
  /// Reporting for [config] into [queue] (tests; apps call
  /// [installAppErrors]).
  AppErrors.forTest(this.config, this.queue, {DateTime Function()? now})
    : reporter = ErrorReporter(queue, config: config, now: now) {
    waits = SlowWaitReporter(queue, now: now, route: () => reporter.route);
  }

  /// The installed instance ([WaitWatch] reads it); null before install.
  static AppErrors? instance;

  /// The app reported for.
  final AppErrorsConfig config;

  /// Reports not yet uploaded.
  final ErrorQueue queue;

  /// Records errors.
  final ErrorReporter reporter;

  /// Times waits.
  late final SlowWaitReporter waits;

  /// Starts uploading to RTDB through [sink] (null while signed out) as
  /// [deviceId]; flushes the backlog after [startDelay].
  ErrorUploader connect({
    required Future<ErrorSink?> Function() sink,
    required Future<String> Function() deviceId,
    Duration startDelay = const Duration(seconds: 20),
  }) => ErrorUploader(queue, config: config, sink: sink, deviceId: deviceId)
    ..start()
    ..schedule(startDelay);
}

/// Installs app-wide reporting for [config] once, from `main` after
/// `WidgetsFlutterBinding.ensureInitialized`: uncaught framework errors
/// (`uncaught.flutter`) and async errors (`uncaught.async`) are queued, then
/// handed to the handlers installed before. Shows nothing on screen.
Future<AppErrors> installAppErrors(
  AppErrorsConfig config, {
  SharedPreferences? preferences,
}) async {
  final queue = await ErrorQueue.open(
    preferences ?? await SharedPreferences.getInstance(),
  );
  final errors = AppErrors.instance = AppErrors.forTest(config, queue);
  final reporter = errors.reporter;
  final framework = FlutterError.onError;
  FlutterError.onError = (details) {
    if (!details.silent) {
      reporter.report(
        'uncaught.flutter',
        details.exception,
        stack: details.stack,
      );
    }
    framework?.call(details);
  };
  final dispatcher = PlatformDispatcher.instance;
  final async = dispatcher.onError;
  dispatcher.onError = (error, stack) {
    reporter.report('uncaught.async', error, stack: stack);
    return async?.call(error, stack) ?? false;
  };
  return errors;
}

/// Keeps the reporter's route current, so every report names its screen.
/// Add it to the app's `navigatorObservers`. Route names only: give routes
/// patterns (`/list/:id`), never ids or titles.
class AppErrorsRouteObserver extends NavigatorObserver {
  /// Stamps routes into [errors].
  AppErrorsRouteObserver(this.errors);

  /// The reporting stamped.
  final AppErrors errors;

  void _set(Route<dynamic>? route) {
    final name = route?.settings.name;
    if (name != null) errors.reporter.route = name;
  }

  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) =>
      _set(route);

  @override
  void didPop(Route<dynamic> route, Route<dynamic>? previousRoute) =>
      _set(previousRoute);

  @override
  void didReplace({Route<dynamic>? newRoute, Route<dynamic>? oldRoute}) =>
      _set(newRoute);
}
