import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sync_settings_ui/sync_settings_ui.dart';

FirebaseRestClient _fakeClient() => FirebaseRestClient(
  databaseUrl: 'https://example.firebasedatabase.app',
  auth: FirebaseTokenProvider(
    apiKey: 'test-key',
    store: InMemoryCredentialStore(),
  ),
);

void main() {
  group('connectWithGoogle', () {
    test('throws StateError when no googleFirebaseFactory is wired', () async {
      final controller = FirebaseSyncController(
        accountLoader: () async => null,
        accountSaver: (_) async {},
        accountClearer: () async {},
        sessionProbe: () async => false,
        firebaseFactory: () async => null,
      );
      expect(controller.supportsGoogle, isFalse);
      expect(controller.connectWithGoogle, throwsStateError);
    });

    test('reports cancelled when the picker returns null', () async {
      final controller = FirebaseSyncController(
        accountLoader: () async => null,
        accountSaver: (_) async {},
        accountClearer: () async {},
        sessionProbe: () async => false,
        firebaseFactory: () async => null,
        googleFirebaseFactory: () async => null,
      );
      expect(controller.supportsGoogle, isTrue);
      final result = await controller.connectWithGoogle();
      expect(result.outcome, FirebaseConnectOutcome.cancelled);
    });

    test('reports connected and the reported email on success', () async {
      final controller = FirebaseSyncController(
        accountLoader: () async =>
            const FirebaseAccount(email: 'g@b.com', password: ''),
        accountSaver: (_) async {},
        accountClearer: () async {},
        sessionProbe: () async => true,
        firebaseFactory: () async => null,
        googleFirebaseFactory: () async => _fakeClient(),
      );
      final result = await controller.connectWithGoogle();
      expect(result.outcome, FirebaseConnectOutcome.connected);
      expect(result.email, 'g@b.com');
    });

    test(
      'reports signedInButNotPersisted with the stale account email when '
      'the client came back non-null but no session actually stuck -- the '
      'invariant this package exists to centralize',
      () async {
        final controller = FirebaseSyncController(
          accountLoader: () async =>
              const FirebaseAccount(email: 'stale@b.com', password: ''),
          accountSaver: (_) async {},
          accountClearer: () async {},
          sessionProbe: () async => false,
          firebaseFactory: () async => null,
          googleFirebaseFactory: () async => _fakeClient(),
        );
        final result = await controller.connectWithGoogle();
        expect(
          result.outcome,
          FirebaseConnectOutcome.signedInButNotPersisted,
        );
        expect(result.email, 'stale@b.com');
      },
    );

    test(
      'reports wrongAccount with the error message on FirebaseAuthError',
      () async {
        final controller = FirebaseSyncController(
          accountLoader: () async => null,
          accountSaver: (_) async {},
          accountClearer: () async {},
          sessionProbe: () async => false,
          firebaseFactory: () async => null,
          googleFirebaseFactory: () async =>
              throw FirebaseAuthError('wrong uid'),
        );
        final result = await controller.connectWithGoogle();
        expect(result.outcome, FirebaseConnectOutcome.wrongAccount);
        expect(result.message, 'wrong uid');
      },
    );

    test(
      'reports failed with the stringified error on any other failure',
      () async {
        final controller = FirebaseSyncController(
          accountLoader: () async => null,
          accountSaver: (_) async {},
          accountClearer: () async {},
          sessionProbe: () async => false,
          firebaseFactory: () async => null,
          googleFirebaseFactory: () async => throw StateError('boom'),
        );
        final result = await controller.connectWithGoogle();
        expect(result.outcome, FirebaseConnectOutcome.failed);
        expect(result.message, contains('boom'));
      },
    );
  });

  group('disconnect', () {
    test('calls the account clearer', () async {
      var cleared = false;
      final controller = FirebaseSyncController(
        accountLoader: () async => null,
        accountSaver: (_) async {},
        accountClearer: () async => cleared = true,
        sessionProbe: () async => false,
        firebaseFactory: () async => null,
      );
      await controller.disconnect();
      expect(cleared, isTrue);
    });
  });
}
