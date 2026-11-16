/// EncryptingStore.getStringMap on a data dir that also holds non-log
/// entries and unreadable ones.
library;

import 'package:crdt_sync/crdt_sync.dart';
import 'package:test/test.dart';

import 'e2e_fakes.dart';

const _old = 'settings-sync';

void main() {
  final layout = E2eLayout.of(_old);

  Future<E2eKey> key(RemoteStore remote) => unlockE2e(
    store: remote,
    pathPrefix: layout.prefix,
    passphrase: 'pw',
    params: cheapArgon,
    e2ePath: layout.e2ePath,
  );

  EncryptingStore open(
    MemoryRemote remote,
    E2eKey k, {
    bool acceptPlaintext = true,
  }) => EncryptingStore(
    remote,
    k,
    pathPrefix: layout.prefix,
    revsPath: layout.revsPath,
    e2ePath: layout.e2ePath,
    acceptPlaintext: acceptPlaintext,
  );

  test('the header inside the prefix passes through undecrypted', () async {
    final remote = MemoryRemote();
    final store = open(remote, await key(remote));
    final log = encodeLog(logOf({'a': 'secret'}));
    await store.putFileText('${layout.prefix}/node.json', log, message: 'm');
    final map = await store.getStringMap(layout.prefix);
    expect(map['e2e'], remote.files[layout.e2ePath]);
    expect(map['node.json'], log);
  });

  test('an unreadable entry is dropped from the bulk read', () async {
    final remote = MemoryRemote();
    final store = open(remote, await key(remote), acceptPlaintext: false);
    remote.files['${layout.prefix}/old.json'] = encodeLog(logOf({'a': 'x'}));
    final map = await store.getStringMap(layout.prefix);
    expect(map.containsKey('old.json'), isFalse);
  });
}
