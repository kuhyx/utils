/// syncLog over an EncryptingStore: the relay sees ciphertext, merge is
/// unchanged.
library;

import 'package:crdt_sync/crdt_sync.dart';
import 'package:glados/glados.dart' hide expect, group, test, setUp;
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

Future<Log> _tick(
  RemoteStore client,
  String deviceId,
  Log local, {
  SyncStateStore? state,
  List<String>? skipped,
}) => syncLog(
  client: client,
  deviceId: deviceId,
  pathPrefix: _prefix,
  localLog: local,
  encode: encodeLog,
  decode: decodeLog,
  stateStore: state,
  onPeerSkipped: (id, _) => skipped?.add(id),
);

void main() {
  test('pushed blob is ciphertext and a peer merges it', () async {
    final remote = MemoryRemote();
    final key = await _key(remote);
    final store = EncryptingStore(remote, key, pathPrefix: _prefix);
    await _tick(store, 'phone', logOf({'n1': 'buy milk'}));

    final blob = remote.files['$_prefix/phone/log.json']!;
    expect(blob, isNot(contains('title')));
    expect(blob, isNot(contains('buy milk')));

    final merged = await _tick(store, 'pc', logOf({'n2': 'call mum'}));
    expect(merged.keys, unorderedEquals(['n1', 'n2']));
    expect(remote.files.values.where((v) => v.contains('"title"')), isEmpty);
  });

  test('published revisions are keyed, not sha256 of the plaintext', () async {
    final remote = MemoryRemote();
    final store = EncryptingStore(
      remote,
      await _key(remote),
      pathPrefix: _prefix,
    );
    final local = logOf({'n1': 'x'});
    await _tick(store, 'phone', local, state: InMemorySyncStateStore());
    final rev = remote.files['$_revs/phone']!;
    expect(rev, isNot(revisionOf(encodeLog(local))));
    expect(rev, hasLength(64));
  });

  test('a peer that has not upgraded is still read', () async {
    final remote = MemoryRemote();
    await _tick(remote, 'pc', logOf({'old': 'plain'}));
    final store = EncryptingStore(
      remote,
      await _key(remote),
      pathPrefix: _prefix,
    );
    final merged = await _tick(store, 'phone', logOf({'n1': 'x'}));
    expect(merged.keys, unorderedEquals(['old', 'n1']));
  });

  test('a tampered peer is skipped and the others still merge', () async {
    final remote = MemoryRemote();
    final store = EncryptingStore(
      remote,
      await _key(remote),
      pathPrefix: _prefix,
    );
    await _tick(store, 'b', logOf({'b1': 'y'}));
    await _tick(store, 'a', logOf({'a1': 'x'}));
    final blob = remote.files['$_prefix/a/log.json']!;
    remote.files['$_prefix/a/log.json'] = blob.replaceRange(
      40,
      41,
      blob[40] == 'A' ? 'B' : 'A',
    );
    final skipped = <String>[];
    final merged = await _tick(store, 'c', {}, skipped: skipped);
    expect(merged.keys, ['b1']);
    expect(skipped, ['a']);
  });

  test('unparsable and mis-shaped peers are reported as skipped', () async {
    final remote = MemoryRemote({
      '$_prefix/bad/log.json': '{oops',
      '$_prefix/shape/log.json': '{"n":{"id":1}}',
    });
    final skipped = <String>[];
    await _tick(remote, 'me', {}, skipped: skipped);
    expect(skipped, unorderedEquals(['bad', 'shape']));
  });

  test('a peer under another passphrase is skipped, not fatal', () async {
    final remote = MemoryRemote();
    final other = MemoryRemote();
    final mine = EncryptingStore(
      remote,
      await _key(remote),
      pathPrefix: _prefix,
    );
    final theirs = EncryptingStore(
      remote,
      await _key(other, 'other'),
      pathPrefix: _prefix,
    );
    await _tick(theirs, 'x', logOf({'x1': 'x'}));
    expect(await _tick(mine, 'me', {}), isEmpty);
  });

  test('a prefix without a slash keeps revs out of the sealed set', () async {
    final remote = MemoryRemote();
    final key = await unlockE2e(
      store: remote,
      pathPrefix: 'wake-alarm',
      passphrase: 'pw',
      params: cheapArgon,
    );
    final store = EncryptingStore(remote, key, pathPrefix: 'wake-alarm');
    await syncLog(
      client: store,
      deviceId: 'phone',
      pathPrefix: 'wake-alarm',
      localLog: logOf({'n': 'x'}),
      encode: encodeLog,
      decode: decodeLog,
      stateStore: InMemorySyncStateStore(),
    );
    expect(remote.files['wake-alarm/revs/phone'], hasLength(64));
    expect(remote.files['wake-alarm/phone/log.json'], isNot(contains('"x"')));
    expect(remote.files['wake-alarm/e2e'], contains('argon2id'));
  });

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

  test('a flat <prefix>/<node>.json layout (todo) is sealed too', () async {
    final remote = MemoryRemote();
    final store = EncryptingStore(
      remote,
      await _key(remote),
      pathPrefix: _prefix,
    );
    final log = encodeLog(logOf({'n1': 'buy milk'}));
    await store.putFileText('$_prefix/node-a.json', log, message: 'm');
    expect(remote.files['$_prefix/node-a.json'], isNot(contains('milk')));
    expect(isE2eEnvelope(remote.files['$_prefix/node-a.json']!), isTrue);
    expect(await store.getFileText('$_prefix/node-a.json'), log);
  });

  test('a slashless prefix keeps the header and revs out of sealing', () async {
    final remote = MemoryRemote();
    final key = await unlockE2e(
      store: remote,
      pathPrefix: 'wake-alarm',
      passphrase: 'pw',
      params: cheapArgon,
    );
    final store = EncryptingStore(remote, key, pathPrefix: 'wake-alarm');
    final header = remote.files['wake-alarm/e2e']!;
    expect(await store.getFileText('wake-alarm/e2e'), header);
    await store.putFileText('wake-alarm/e2e', header, message: 'm');
    expect(remote.files['wake-alarm/e2e'], header);
  });

  test('plaintext is refused when acceptPlaintext is off', () async {
    final remote = MemoryRemote({
      '$_prefix/pc/log.json': encodeLog(logOf({'a': 'b'})),
    });
    final store = EncryptingStore(
      remote,
      await _key(remote),
      pathPrefix: _prefix,
      acceptPlaintext: false,
    );
    expect(await _tick(store, 'phone', {}), isEmpty);
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

  // Differential: the same sync rounds over a plain and an encrypting relay
  // must converge to the same logs.
  Glados(
    any.list(
      any.combine3(
        any.intInRange(0, 3),
        any.intInRange(0, 6),
        any.letterOrDigits,
        (int d, int n, String t) => (d, n, t),
      ),
    ),
    ExploreConfig(numRuns: 25),
  ).test('merge is identical with and without encryption', (edits) async {
    const devices = ['a', 'b', 'c'];
    Log localFor(int d) => {
      for (final (i, (dev, note, title)) in edits.indexed)
        if (dev == d)
          'n$note': Record(
            id: 'n$note',
            fields: {
              'title': (
                title,
                Hlc(wallTimeMs: 1000 + i, counter: 0, nodeId: devices[d]),
              ),
            },
          ),
    };
    final plain = MemoryRemote();
    final sealedRemote = MemoryRemote();
    final sealed = EncryptingStore(
      sealedRemote,
      await E2eKey.fromBytes(List<int>.filled(32, 3)),
      pathPrefix: _prefix,
    );
    final plainLogs = [for (var d = 0; d < 3; d++) localFor(d)];
    final sealedLogs = [for (var d = 0; d < 3; d++) localFor(d)];
    for (var round = 0; round < 2; round++) {
      for (var d = 0; d < 3; d++) {
        plainLogs[d] = await _tick(plain, devices[d], plainLogs[d]);
        sealedLogs[d] = await _tick(sealed, devices[d], sealedLogs[d]);
      }
    }
    expect(sealedLogs, plainLogs);
    expect(sealedLogs[0], sealedLogs[2]);
  });
}
