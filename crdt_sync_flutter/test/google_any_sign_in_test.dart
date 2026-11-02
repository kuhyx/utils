import 'package:crdt_sync_flutter/crdt_sync_flutter.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_account_token/google_account_token.dart'
    show kGoogleAccountTokenChannel;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  // `flutter test` reports Android as the default target platform, so the
  // desktop configuration this suite exercises is pinned explicitly: the
  // plugin half is false and the loopback half is live. The Android routing
  // has its own group at the bottom.
  setUp(() => debugDefaultTargetPlatformOverride = TargetPlatform.linux);
  tearDown(() {
    debugDefaultTargetPlatformOverride = null;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(kGoogleAccountTokenChannel, null);
  });

  group('desktopSignInSupported', () {
    test('is true on this host once a desktop client id exists', () {
      expect(desktopSignInSupported('desktop-cid'), isTrue);
    });

    test('is false without a desktop client id', () {
      // The guard against a button that can only ever fail.
      expect(desktopSignInSupported(''), isFalse);
    });
  });

  group('googleAnySignInSupported', () {
    test('is true when only the desktop half is configured', () {
      expect(
        googleAnySignInSupported(
          serverClientId: '',
          desktopClientId: 'desktop-cid',
        ),
        isTrue,
      );
    });

    test('is false when neither half is configured', () {
      expect(
        googleAnySignInSupported(serverClientId: '', desktopClientId: ''),
        isFalse,
      );
    });

    test('is false on this host when only the plugin half is configured', () {
      // The plugin does not run on Linux, so a Web client id alone buys
      // nothing here -- and the button must not appear.
      expect(
        googleAnySignInSupported(
          serverClientId: 'web-cid',
          desktopClientId: '',
        ),
        isFalse,
      );
    });
  });

  group('googleFlowFor', () {
    test('picks the desktop flow on this host', () {
      expect(
        googleFlowFor(serverClientId: '', desktopClientId: 'd'),
        GoogleFlow.desktop,
      );
    });

    test('picks nothing when neither half is configured', () {
      expect(
        googleFlowFor(serverClientId: '', desktopClientId: ''),
        GoogleFlow.none,
      );
    });

    test('picks nothing when only the plugin half is configured here', () {
      // The plugin does not run on Linux, so a Web client id alone must not
      // route anywhere -- that would be a button that cannot succeed.
      expect(
        googleFlowFor(serverClientId: 'web-cid', desktopClientId: ''),
        GoogleFlow.none,
      );
    });
  });

  group('googleAnyIdToken', () {
    test('returns null when no flow is available', () async {
      expect(
        await googleAnyIdToken(serverClientId: '', desktopClientId: ''),
        isNull,
      );
    });

    test('returns null when the plugin half alone is configured', () async {
      // Would reach the plugin's platform channel if the gate were wrong,
      // which throws rather than returning null.
      expect(
        await googleAnyIdToken(serverClientId: 'web-cid', desktopClientId: ''),
        isNull,
      );
    });
  });

  group('on Android', () {
    setUp(() => debugDefaultTargetPlatformOverride = TargetPlatform.android);

    test('the plugin flow wins and the desktop one is off', () {
      expect(
        googleFlowFor(serverClientId: 'web-cid', desktopClientId: 'd'),
        GoogleFlow.plugin,
      );
      expect(desktopSignInSupported('d'), isFalse);
      expect(
        googleAnySignInSupported(
          serverClientId: 'web-cid',
          desktopClientId: '',
        ),
        isTrue,
      );
    });

    test('googleAnyIdToken reaches the AccountManager plugin', () async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(
            kGoogleAccountTokenChannel,
            (_) async => 'native-token',
          );
      expect(
        await googleAnyIdToken(serverClientId: 'web-cid', desktopClientId: ''),
        'native-token',
      );
    });
  });
}
