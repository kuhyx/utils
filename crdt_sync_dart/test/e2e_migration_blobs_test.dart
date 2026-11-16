/// Migration over flat `<node>.json` leaves and non-log source blobs.
library;

import 'package:crdt_sync/crdt_sync.dart';
import 'package:test/test.dart';

import 'e2e_fakes.dart';

const _old = 'app/notes';

void main() {
  final layout = E2eLayout.of(_old);

  Future<E2eKey> key(RemoteStore remote) => unlockE2e(
    store: remote,
    pathPrefix: layout.prefix,
    passphrase: 'pw',
    params: cheapArgon,
    e2ePath: layout.e2ePath,
  );

  test('a flat leaf is read one by one when the backend has no bulk', () async {
    final inner = MemoryRemote({
      '$_old/node.json': encodeLog(logOf({'a': 'milk'})),
    });
    final remote = PlainRemote(inner);
    final report = await copyToEncrypted(
      store: remote,
      key: await key(remote),
      fromPrefix: _old,
      layout: layout,
    );
    expect(report.copied, 1);
    final blob = inner.files['${layout.prefix}/node.json']!;
    expect(blob, isNot(contains('milk')));
  });

  test('a source blob that is not a JSON object is skipped', () async {
    final remote = MemoryRemote({
      '$_old/list/log.json': '[1,2]',
      '$_old/shape/log.json': '{"a":5}',
    });
    final report = await copyToEncrypted(
      store: remote,
      key: await key(remote),
      fromPrefix: _old,
      layout: layout,
    );
    expect(report.copied, 0);
    expect(
      report.skipped,
      unorderedEquals(['list/log.json', 'shape/log.json']),
    );
  });
}
