import 'package:crdt_sync_flutter/crdt_sync_flutter.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  // Under `flutter test` the io platform gate answers for the host, which is
  // Linux -- so the plugin half is false and the loopback half is live. That
  // is the desktop configuration, and it is the one this suite can exercise
  // honestly; the Android half is asserted on the device instead.
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
      expect(googleAnySignInSupported(serverClientId: ''), isFalse);
    });

    test('is false on this host when only the plugin half is configured', () {
      // The plugin does not run on Linux, so a Web client id alone buys
      // nothing here -- and the button must not appear.
      expect(googleAnySignInSupported(serverClientId: 'web-cid'), isFalse);
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
      expect(googleFlowFor(serverClientId: ''), GoogleFlow.none);
    });

    test('picks nothing when only the plugin half is configured here', () {
      // The plugin does not run on Linux, so a Web client id alone must not
      // route anywhere -- that would be a button that cannot succeed.
      expect(googleFlowFor(serverClientId: 'web-cid'), GoogleFlow.none);
    });
  });

  group('googleAnyIdToken', () {
    test('returns null when no flow is available', () async {
      expect(await googleAnyIdToken(serverClientId: ''), isNull);
    });

    test('returns null when the plugin half alone is configured', () async {
      // Would reach the plugin's platform channel if the gate were wrong,
      // which throws rather than returning null.
      expect(await googleAnyIdToken(serverClientId: 'web-cid'), isNull);
    });
  });
}
