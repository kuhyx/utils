import 'dart:ui' show PlatformDispatcher;

import 'package:crdt_sync_flutter/crdt_sync_flutter.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'app_errors_support.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues({}));

  group('build number fallback', () {
    const bare = AppErrorsConfig(app: 'todo', repo: 'kuhyx/todo');

    Future<AppErrors> install(
      AppErrorsConfig c,
      Future<String?> Function() buildNumber,
    ) async {
      final saved = (FlutterError.onError, PlatformDispatcher.instance.onError);
      final errors = await installAppErrors(
        c,
        preferences: await SharedPreferences.getInstance(),
        buildNumber: buildNumber,
      );
      FlutterError.onError = saved.$1;
      PlatformDispatcher.instance.onError = saved.$2;
      AppErrors.instance = null;
      return errors;
    }

    test('no APP_BUILD: the installed versionCode is used', () async {
      final errors = await install(bare, () async => '173');
      expect(errors.config.build, 173);
      expect(errors.config.app, 'todo');
    });

    test('an explicit build wins over the installed one', () async {
      final errors = await install(config, () async => '173');
      expect(errors.config.build, 42);
    });

    test('an unreadable versionCode stays 0', () async {
      expect((await install(bare, () async => 'x')).config.build, 0);
      expect((await install(bare, () async => null)).config.build, 0);
      expect(
        (await install(bare, () async => throw StateError('no'))).config.build,
        0,
      );
    });
  });

  test('the default versionCode comes from the platform', () async {
    PackageInfo.setMockInitialValues(
      appName: 'todo',
      packageName: 'com.kuhy.todo',
      version: '1.0.0',
      buildNumber: '9',
      buildSignature: '',
    );
    expect(await platformBuildNumber(), '9');
  });
}
