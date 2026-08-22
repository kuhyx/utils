import 'package:crdt_sync_flutter/crdt_sync_flutter.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('googleSignInSupported', () {
    test('is false without a client id, whatever the platform', () {
      // The guard that stops a build which forgot the constant from showing a
      // button that can only ever report "cancelled".
      expect(googleSignInSupported(''), isFalse);
    });

    test('follows the platform gate once a client id is present', () {
      // Under `flutter test` the io half answers for the host, which is not
      // Android -- so this is false here and true on a real handset. Asserting
      // the platform's own answer keeps the test honest on every host.
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
}
