import 'package:crdt_sync_flutter/crdt_sync_flutter.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_account_token/google_account_token.dart'
    show kGoogleAccountTokenChannel;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  tearDown(() {
    debugDefaultTargetPlatformOverride = null;
    messenger.setMockMethodCallHandler(kGoogleAccountTokenChannel, null);
  });

  group('googleSignInSupported', () {
    test('is true on Android once a client id is present', () {
      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      expect(googleSignInSupported('some-client-id'), isTrue);
    });

    test('is false on iOS: AccountManager is Android-only', () {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      expect(googleSignInSupported('some-client-id'), isFalse);
    });

    test('is false without a client id, whatever the platform', () {
      // The guard that stops a build which forgot the constant from showing a
      // button that can only ever report "cancelled".
      expect(googleSignInSupported(''), isFalse);
    });

    test('is false on a desktop host even with a client id', () {
      debugDefaultTargetPlatformOverride = TargetPlatform.linux;
      expect(googleSignInSupported('some-client-id'), isFalse);
    });
  });

  group('googleIdToken', () {
    test('returns the token the injected sign-in yields', () async {
      final token = await googleIdToken(
        serverClientId: 'cid',
        signInFn: () async => 'the-token',
      );
      expect(token, 'the-token');
    });

    test('returns null when the user dismisses the picker', () async {
      final token = await googleIdToken(
        serverClientId: 'cid',
        signInFn: () async => null,
      );
      expect(token, isNull);
    });

    test('returns null, without touching the plugin, on an empty id', () async {
      // Reaching the plugin here would throw MissingPluginException rather
      // than returning null, so this also proves the guard runs first.
      expect(await googleIdToken(serverClientId: ''), isNull);
    });
  });

  group('googleIdToken through the AccountManager plugin', () {
    setUp(() => debugDefaultTargetPlatformOverride = TargetPlatform.android);

    test('asks the native side for a token for the web client', () async {
      MethodCall? seen;
      messenger.setMockMethodCallHandler(kGoogleAccountTokenChannel, (
        call,
      ) async {
        seen = call;
        return 'native-token';
      });
      final token = await googleIdToken(serverClientId: 'web-cid');
      expect(token, 'native-token');
      expect(seen?.method, 'idToken');
      expect(seen?.arguments, {'serverClientId': 'web-cid'});
    });

    test('a failing native side is null, not a throw', () async {
      messenger.setMockMethodCallHandler(
        kGoogleAccountTokenChannel,
        (_) async => throw PlatformException(code: 'auth_failed'),
      );
      expect(await googleIdToken(serverClientId: 'web-cid'), isNull);
    });
  });
}
