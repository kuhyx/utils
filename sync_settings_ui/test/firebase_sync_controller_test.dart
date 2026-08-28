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
  group('loadStatus', () {
    test('reports connected with the stored email', () async {
      final controller = FirebaseSyncController(
        accountLoader: () async =>
            const FirebaseAccount(email: 'a@b.com', password: 'x'),
        accountSaver: (_) async {},
        accountClearer: () async {},
        sessionProbe: () async => true,
        firebaseFactory: () async => null,
      );
      final status = await controller.loadStatus();
      expect(status.connected, isTrue);
      expect(status.email, 'a@b.com');
    });

    test(
      'reports not connected with a null email when nothing stored',
      () async {
        final controller = FirebaseSyncController(
          accountLoader: () async => null,
          accountSaver: (_) async {},
          accountClearer: () async {},
          sessionProbe: () async => false,
          firebaseFactory: () async => null,
        );
        final status = await controller.loadStatus();
        expect(status.connected, isFalse);
        expect(status.email, isNull);
      },
    );

    test(
      'trusts the session probe over account presence -- a marker with no '
      'live session must read as not connected',
      () async {
        final controller = FirebaseSyncController(
          accountLoader: () async =>
              const FirebaseAccount(email: 'stale@b.com', password: 'x'),
          accountSaver: (_) async {},
          accountClearer: () async {},
          sessionProbe: () async => false,
          firebaseFactory: () async => null,
        );
        final status = await controller.loadStatus();
        expect(status.connected, isFalse);
      },
    );
  });

  group('connectWithPassword', () {
    test('saves the account and reports connected on success', () async {
      FirebaseAccount? saved;
      final controller = FirebaseSyncController(
        accountLoader: () async => null,
        accountSaver: (account) async => saved = account,
        accountClearer: () async {},
        sessionProbe: () async => true,
        firebaseFactory: () async => _fakeClient(),
      );
      final result = await controller.connectWithPassword(
        email: 'a@b.com',
        password: 'pw',
      );
      expect(result.outcome, FirebaseConnectOutcome.connected);
      expect(result.email, 'a@b.com');
      expect(saved?.email, 'a@b.com');
    });

    test(
      'clears the account and reports rejected when the client is null',
      () async {
        var cleared = false;
        final controller = FirebaseSyncController(
          accountLoader: () async => null,
          accountSaver: (_) async {},
          accountClearer: () async => cleared = true,
          sessionProbe: () async => false,
          firebaseFactory: () async => null,
        );
        final result = await controller.connectWithPassword(
          email: 'a@b.com',
          password: 'wrong',
        );
        expect(result.outcome, FirebaseConnectOutcome.rejected);
        expect(cleared, isTrue);
      },
    );

    test(
      'clears the account and reports rejected with the error message when '
      'firebaseFactory throws FirebaseAuthError -- reproduces the screen '
      'getting stuck on "Signing in..." forever, since nothing here used '
      'to catch this',
      () async {
        var cleared = false;
        final controller = FirebaseSyncController(
          accountLoader: () async => null,
          accountSaver: (_) async {},
          accountClearer: () async => cleared = true,
          sessionProbe: () async => false,
          firebaseFactory: () async => throw FirebaseAuthError('wrong password'),
        );
        final result = await controller.connectWithPassword(
          email: 'a@b.com',
          password: 'wrong',
        );
        expect(result.outcome, FirebaseConnectOutcome.rejected);
        expect(result.message, 'wrong password');
        expect(cleared, isTrue);
      },
    );

    test(
      'reports failed with the stringified error, and does not clear the '
      'account, on any other failure -- a possibly-transient error is not '
      'proof the credentials are wrong',
      () async {
        var cleared = false;
        final controller = FirebaseSyncController(
          accountLoader: () async => null,
          accountSaver: (_) async {},
          accountClearer: () async => cleared = true,
          sessionProbe: () async => false,
          firebaseFactory: () async => throw StateError('boom'),
        );
        final result = await controller.connectWithPassword(
          email: 'a@b.com',
          password: 'pw',
        );
        expect(result.outcome, FirebaseConnectOutcome.failed);
        expect(result.message, contains('boom'));
        expect(cleared, isFalse);
      },
    );

    test('reports progress stages in order on success', () async {
      final stages = <String>[];
      final controller = FirebaseSyncController(
        accountLoader: () async => null,
        accountSaver: (_) async {},
        accountClearer: () async {},
        sessionProbe: () async => true,
        firebaseFactory: () async => _fakeClient(),
      );
      await controller.connectWithPassword(
        email: 'a@b.com',
        password: 'pw',
        onProgress: stages.add,
      );
      expect(stages, ['Saving account…', 'Signing in to Firebase…']);
    });
  });
}
