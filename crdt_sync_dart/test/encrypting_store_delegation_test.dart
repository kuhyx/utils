/// EncryptingStore forwards what it does not seal to the inner store.
library;

import 'package:crdt_sync/crdt_sync.dart';
import 'package:glados/glados.dart' show Random;
import 'package:test/test.dart';

import 'e2e_fakes.dart';

const _prefix = 'todo-sync/notes';
const _revs = 'todo-sync/revs';

Future<E2eKey> _key(MemoryRemote remote, [String passphrase = 'pw']) =>
    unlockE2e(
      store: remote,
      pathPrefix: _prefix,
      passphrase: passphrase,
      params: cheapArgon,
      random: Random(1),
    );

void main() {
  test('paths outside the prefix pass through untouched', () async {
    final remote = MemoryRemote();
    final store = EncryptingStore(
      remote,
      await _key(remote),
      pathPrefix: _prefix,
    );
    await store.putFileText('other/x', '{"a":1}', message: 'm');
    expect(remote.files['other/x'], '{"a":1}');
    expect(await store.getFileText('other/x'), '{"a":1}');
    expect(await store.getFileText('$_prefix/none/log.json'), isNull);
  });

  group('delegation', () {
    test('bulk reads forward when the inner store has them', () async {
      final remote = MemoryRemote({'$_revs/a': 'r'});
      final store = EncryptingStore(
        remote,
        await _key(remote),
        pathPrefix: _prefix,
      );
      expect(await store.getStringMap(_revs), {'a': 'r'});
    });

    test('bulk reads degrade to "fetch everything" without them', () async {
      final remote = MemoryRemote({'$_revs/a': 'r'});
      final store = EncryptingStore(
        PlainRemote(remote),
        await _key(remote),
        pathPrefix: _prefix,
      );
      expect(await store.getStringMap(_revs), isEmpty);
    });

    test('list, delete, access and close reach the inner store', () async {
      final remote = MemoryRemote({'$_prefix/a/log.json': '{}'});
      final store = EncryptingStore(
        remote,
        await _key(remote),
        pathPrefix: _prefix,
      );
      expect(await store.listDirectory(_prefix), ['a']);
      await store.deleteFile('$_prefix/a/log.json', message: 'm');
      expect(remote.files.containsKey('$_prefix/a/log.json'), isFalse);
      expect(await store.canAccessRemote(), isTrue);
      store.close();
      expect(remote.closed, isTrue);
    });
  });
}
