import 'package:crdt_sync_flutter/testing/fake_secure_storage.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const storage = FlutterSecureStorage();

  test('serves the whole channel surface the plugin exposes', () async {
    // The fake ships from lib/, so consuming apps rely on it for their own
    // sync tests: every method the plugin can call has to answer.
    installFakeSecureStorage(initial: {'seeded': 'value'});

    expect(await storage.read(key: 'seeded'), 'value');
    expect(await storage.containsKey(key: 'seeded'), isTrue);

    await storage.write(key: 'k', value: 'v');
    expect(await storage.readAll(), {'seeded': 'value', 'k': 'v'});

    await storage.delete(key: 'k');
    expect(await storage.containsKey(key: 'k'), isFalse);

    await storage.deleteAll();
    expect(await storage.readAll(), isEmpty);
  });

  test('throwing mode simulates a host with no secret service', () async {
    installFakeSecureStorage(throwing: true);

    await expectLater(storage.read(key: 'anything'), throwsA(isA<Object>()));
  });
}
