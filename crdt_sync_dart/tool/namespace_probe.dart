// Helper for test/sync_namespace_test.dart: the SYNC_NAMESPACE define is
// compile-time, so the test runs this in a fresh process with -D set. It signs
// in from an in-memory session (no network) and prints the first request path.
import 'package:crdt_sync/crdt_sync.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart' as http_testing;

Future<void> main() async {
  final mock = http_testing.MockClient((request) async {
    print(request.url.path);
    return http.Response('null', 200);
  });
  final client = await firebaseClientFor(
    config: const FirebaseConfig(
      apiKey: 'k',
      databaseUrl: 'https://example.firebasedatabase.app',
      projectId: 'p',
      uid: 'u',
      email: 'e@x.y',
    ),
    store: InMemoryCredentialStore(
      FirebaseCredentials(
        idToken: 'i',
        refreshToken: 'r',
        expiresAt: DateTime.utc(2099),
      ),
    ),
    httpClient: mock,
  );
  await client.listDirectory('devices');
}
