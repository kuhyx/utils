/// Writes cross-language golden vectors for the Python port to open.
///
/// Run: `dart run tool/e2e_vectors.dart > test/fixtures/e2e_dart_vectors.json`
library;

import 'dart:convert';
import 'dart:math';

import 'package:crdt_sync/crdt_sync.dart';

import '../test/e2e_fakes.dart';

Future<void> main() async {
  const params = Argon2Params(memoryKiB: 64, iterations: 2, parallelism: 1);
  final remote = MemoryRemote();
  final key = await unlockE2e(
    store: remote,
    pathPrefix: 'vec/notes-e2e',
    passphrase: 'correct horse ✓',
    params: params,
    random: Random(7),
    e2ePath: 'vec/e2e',
  );
  final cipher = key.cipher();
  const path = 'vec/notes-e2e/phone/log.json';
  final log = encodeLog(logOf({'n1': 'buy milk', 'n2': 'zażółć'}));
  print(
    const JsonEncoder.withIndent('  ').convert({
      'passphrase': 'correct horse ✓',
      'header': remote.files['vec/e2e'],
      'master_hex': key.bytes
          .map((b) => b.toRadixString(16).padLeft(2, '0'))
          .join(),
      'revision_of_abc': await key.revision('abc'),
      'path': path,
      'log': log,
      'envelope': await sealLogText(log, cipher, path: path),
      'whole': await sealLogText('not a log', cipher, path: path),
    }),
  );
}
