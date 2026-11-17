import 'dart:convert';
import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart' show Argon2Params, E2eCipher;
import 'package:rtdb_relay/src/rtdb_client.dart';
import 'package:rtdb_relay/src/sealer.dart';

import 'fake_rtdb.dart';
import 'tutor_layout.dart';

const fastArgon = Argon2Params(memoryKiB: 8, iterations: 1, parallelism: 1);
const testRid = '01J0000000000000000000000R';

final Map<String, dynamic> e2eVectors = jsonDecode(
  File('test/data/e2e_vectors.json').readAsStringSync(),
) as Map<String, dynamic>;

RelaySealer vectorSealer() => RelaySealer(
  E2eCipher(hexBytes(e2eVectors['key_hex'] as String)),
  layout: tutorLayout,
);

List<int> hexBytes(String s) => [
  for (var i = 0; i < s.length; i += 2)
    int.parse(s.substring(i, i + 2), radix: 16),
];

RtdbClient sealedClient(FakeRtdb db) => db.client()..sealer = vectorSealer();
