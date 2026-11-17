import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart' show E2eLayout, E2eLockReason;
import 'package:crdt_sync_flutter/crdt_sync_flutter.dart'
    show kE2ePassphraseKey;
import 'package:crdt_sync_flutter/testing/fake_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:rtdb_relay/src/e2e_gate.dart';
import 'package:rtdb_relay/src/json_tree.dart';
import 'package:rtdb_relay/src/layout.dart';
import 'package:rtdb_relay/src/rtdb_client.dart';

import 'support/e2e_fixture.dart';
import 'support/fake_rtdb.dart';
import 'support/tutor_layout.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('a client that needs a key sends nothing without one', () async {
    final db = FakeRtdb();
    final client = RtdbClient(
      layout: tutorLayout,
      databaseUrl: 'https://fake',
      idToken: () async => 'tok',
      httpClient: db.client().httpClient,
      namespace: '',
      sealRequired: true,
    );
    await expectLater(
      client.put('tutor/v1-e2e/requests/$testRid/req', {'kind': 'x'}),
      throwsA(isA<RtdbError>()),
    );
    await expectLater(
      client.get('tutor/v1-e2e/live'),
      throwsA(isA<RtdbError>()),
    );
    await expectLater(
      client.delete('tutor/v1-e2e/live'),
      throwsA(isA<RtdbError>()),
    );
    expect(db.log, isEmpty);
    expect(E2eGate(client: client).locked, isTrue);
    expect(E2eGate(client: db.client()).locked, isFalse);
    expect(await E2eGate(client: db.client()).unlock(), isTrue);
  });

  group('E2eGate', () {
    RtdbClient needy(FakeRtdb db) => RtdbClient(
      layout: tutorLayout,
      databaseUrl: 'https://fake',
      idToken: () async => 'tok',
      httpClient: db.client().httpClient,
      namespace: '',
      sealRequired: true,
    );

    test('unlocks from the keystore and makes the header once', () async {
      installFakeSecureStorage(initial: {kE2ePassphraseKey: 'test-passphrase'});
      final db = FakeRtdb();
      final client = needy(db);
      final gate = E2eGate(client: client, params: fastArgon);
      expect(await gate.unlock(), isTrue);
      expect(gate.locked, isFalse);
      expect(await gate.unlock(), isTrue); // already open
      final header = getAt(db.root, E2eLayout.of(tutorLayout.base).e2ePath);
      expect(header, isA<String>());
      await client.put('tutor/v1-e2e/live', {'session': 'x'});
      expect(
        jsonEncode(getAt(db.root, 'tutor/v1-e2e/live')),
        contains(kSealedKey),
      );
      // A second device with the same passphrase reads the same key.
      final other = needy(db);
      expect(await E2eGate(client: other, params: fastArgon).unlock(), isTrue);
      expect(await other.get('tutor/v1-e2e/live'), {'session': 'x'});
    });

    test('stays locked without, or with a wrong, passphrase', () async {
      installFakeSecureStorage();
      final db = FakeRtdb();
      final gate = E2eGate(client: needy(db), params: fastArgon);
      expect(await gate.unlock(), isFalse);
      expect(gate.reason, E2eLockReason.needsPassphrase.name);
      db.root = setAt(db.root, E2eLayout.of(tutorLayout.base).e2ePath, {
        'not': 'a header',
      });
      installFakeSecureStorage(initial: {kE2ePassphraseKey: 'x'});
      final bad = E2eGate(client: needy(db), params: fastArgon);
      expect(await bad.unlock(), isFalse);
      expect(bad.reason, E2eLockReason.badHeader.name);
    });

    test('opens a header and a unit the Python worker made', () async {
      final h = e2eVectors['header'] as Map<String, dynamic>;
      installFakeSecureStorage(
        initial: {kE2ePassphraseKey: h['passphrase'] as String},
      );
      final db = FakeRtdb()..root = setAt(null, h['path'] as String, h['text']);
      final unit = h['unit'] as Map<String, dynamic>;
      db.root = setAt(db.root, 'tutor/v1-e2e/${unit['path']}', unit['stored']);
      final client = needy(db);
      expect(await E2eGate(client: client, params: fastArgon).unlock(), isTrue);
      expect(await client.get('tutor/v1-e2e/${unit['path']}'), unit['value']);
      installFakeSecureStorage(initial: {kE2ePassphraseKey: 'wrong'});
      final wrong = E2eGate(client: needy(db), params: fastArgon);
      expect(await wrong.unlock(), isFalse);
      expect(wrong.reason, E2eLockReason.wrongKey.name);
    });
  });

  test('the header store reads strings only and never deletes', () async {
    final db = FakeRtdb()..root = setAt(null, 'tutor/e2e', {'x': 1});
    final store = E2eHeaderStore(db.client());
    expect(await store.getFileText('tutor/e2e'), '{x: 1}');
    expect(await store.getFileText('tutor/none'), isNull);
    expect(await store.listDirectory('tutor'), isEmpty);
    expect(await store.canAccessRemote(), isTrue);
    expect(() => store.deleteFile('tutor/e2e'), throwsA(anything));
    store.close();
    expect(const E2eLayoutError('x').toString(), 'E2eLayoutError: x');
  });
}
