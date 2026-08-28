import 'package:crdt_sync/crdt_sync.dart';
import 'package:crdt_sync_flutter/crdt_sync_flutter.dart';
import 'package:flutter_test/flutter_test.dart';

/// Built at runtime, not as a top-level `const`.
///
/// Other suites describe their app with a compile-time `const SyncApp(...)`,
/// which the VM folds into a constant before any test body runs -- so the
/// constructors never register as executed and read as uncovered. These
/// helpers force real invocation.
SyncApp _app({WrapperRoutes? routes}) => SyncApp(
  project: const FirebaseProject(
    apiKey: 'test-key',
    databaseUrl: 'https://example-rtdb.europe-west1.firebasedatabase.app',
  ),
  expectedUid: 'uid-123',
  routes: routes,
);

void main() {
  group('SyncApp', () {
    test('keeps the project and uid it was built with', () {
      final app = _app();
      expect(app.project.apiKey, 'test-key');
      expect(app.expectedUid, 'uid-123');
    });

    test('routes default to null for an app with no desktop wrapper', () {
      expect(_app().routes, isNull);
    });

    test('keeps the routes it was given', () {
      final routes = WrapperRoutes(credentialsPath: '/sync-credentials');
      expect(_app(routes: routes).routes, same(routes));
    });
  });

  group('WrapperRoutes', () {
    test('accountPath defaults to null', () {
      final routes = WrapperRoutes(credentialsPath: '/sync-credentials');
      expect(routes.credentialsPath, '/sync-credentials');
      expect(routes.accountPath, isNull);
    });

    test('keeps both paths when the legacy one is supplied', () {
      final routes = WrapperRoutes(
        credentialsPath: '/sync-credentials',
        accountPath: '/sync-account',
      );
      expect(routes.credentialsPath, '/sync-credentials');
      expect(routes.accountPath, '/sync-account');
    });
  });
}
