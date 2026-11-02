import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_account_token/google_account_token.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  final calls = <MethodCall>[];

  void fakeChannel(Future<Object?> Function(MethodCall) handler) {
    messenger.setMockMethodCallHandler(kGoogleAccountTokenChannel, (call) {
      calls.add(call);
      return handler(call);
    });
  }

  tearDown(() {
    calls.clear();
    debugDefaultTargetPlatformOverride = null;
    messenger.setMockMethodCallHandler(kGoogleAccountTokenChannel, null);
  });

  group('googleIdToken on Android', () {
    setUp(() => debugDefaultTargetPlatformOverride = TargetPlatform.android);

    test('asks the platform for a token for the web client', () async {
      fakeChannel((_) async => 'jwt');
      final token = await googleIdToken(serverClientId: 'web-id');
      expect(token, 'jwt');
      expect(calls.single.method, 'idToken');
      expect(calls.single.arguments, {'serverClientId': 'web-id'});
    });

    test('passes the account hint when given', () async {
      fakeChannel((_) async => 'jwt');
      await googleIdToken(serverClientId: 'web-id', accountHint: 'a@b.c');
      expect(calls.single.arguments, {
        'serverClientId': 'web-id',
        'accountHint': 'a@b.c',
      });
    });

    test('a cancelled chooser is null, not an error', () async {
      fakeChannel((_) async => null);
      expect(await googleIdToken(serverClientId: 'x'), isNull);
    });

    test('a platform failure is null, not a throw', () async {
      fakeChannel((_) async => throw PlatformException(code: 'auth_failed'));
      expect(await googleIdToken(serverClientId: 'x'), isNull);
    });

    test('a missing native plugin is null, not a throw', () async {
      expect(await googleIdToken(serverClientId: 'x'), isNull);
    });

    test('an empty client id is null and never reaches the platform', () async {
      fakeChannel((_) async => 'jwt');
      expect(await googleIdToken(serverClientId: ''), isNull);
      expect(calls, isEmpty);
    });
  });

  group('off Android', () {
    for (final platform in [TargetPlatform.linux, TargetPlatform.iOS]) {
      test(
        '$platform is unsupported and returns null without a call',
        () async {
          debugDefaultTargetPlatformOverride = platform;
          fakeChannel((_) async => 'jwt');
          expect(googleAccountTokenSupported, isFalse);
          expect(await googleIdToken(serverClientId: 'x'), isNull);
          expect(calls, isEmpty);
        },
      );
    }

    test('Android is supported', () {
      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      expect(googleAccountTokenSupported, isTrue);
    });
  });
}
