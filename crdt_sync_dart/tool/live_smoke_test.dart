/// End-to-end smoke test against the real Firebase Realtime Database.
///
/// Mocked tests prove the client's branches; this proves the thing actually
/// works against Google's servers -- key escaping, auth, shallow listing, and
/// the revision-based traffic savings that the free-tier headroom depends on.
///
/// Usage:
///   `dart run tool/live_smoke_test.dart <apiKey> <email> <password>`
///
/// Writes only under `_smoketest/`, and deletes what it wrote on the way out.
library;

import 'dart:convert';
import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';

/// Environment-specific values live in a local 0600 config file rather than
/// in source, because this repository is public.
final _configDir = '${Platform.environment['HOME']}/.config/crdt-sync';
const _prefix = '_smoketest/devices';

var _failures = 0;

void _check(String what, bool ok, [String detail = '']) {
  stdout.writeln('${ok ? "  ok  " : "  FAIL"}  $what${detail.isEmpty ? '' : '  ($detail)'}');
  if (!ok) _failures++;
}

Log _log(String id, String value, String nodeId) => {
  id: Record(
    id: id,
    fields: {
      'value': (value, Hlc(wallTimeMs: 1000, counter: 0, nodeId: nodeId)),
    },
  ),
};

String _encode(Log log) =>
    jsonEncode(log.map((id, record) => MapEntry(id, record.toJson())));

Log _decode(String text) => (jsonDecode(text) as Map<String, dynamic>).map(
  (id, data) => MapEntry(id, Record.fromJson(data as Map<String, dynamic>)),
);

Future<void> main(List<String> args) async {
  if (args.length != 3) {
    stderr.writeln(
      'usage: dart run tool/live_smoke_test.dart <apiKey> <email> <password>',
    );
    exit(2);
  }
  final [apiKey, email, password] = args;
  final cfg =
      jsonDecode(File('$_configDir/firebase.json').readAsStringSync())
          as Map<String, dynamic>;

  final auth = FirebaseTokenProvider(
    apiKey: apiKey,
    store: InMemoryCredentialStore(),
  );
  final client = FirebaseRestClient(
    databaseUrl: cfg['databaseUrl'] as String,
    auth: auth,
  );

  stdout.writeln('\n== auth ==');
  _check('canAccessRemote is false before sign-in', !await auth.hasSession());
  await auth.signIn(email: email, password: password);
  _check('signIn stored a session', await auth.hasSession());
  _check('canAccessRemote is true after sign-in', await client.canAccessRemote());

  stdout.writeln('\n== round-trip and key escaping ==');
  const path = '$_prefix/pc/log.json';
  await client.putFileText(path, '{"hello":"world"}', message: 'smoke');
  final read = await client.getFileText(path);
  _check('a .json filename round-trips byte-for-byte',
      read == '{"hello":"world"}', read ?? 'null');
  _check('missing path reads as null',
      await client.getFileText('$_prefix/nope/log.json') == null);
  final listed = await client.listDirectory(_prefix);
  _check('listDirectory sees the device', listed.contains('pc'), '$listed');

  stdout.writeln('\n== sync: first tick pushes ==');
  final storePc = InMemorySyncStateStore();
  await client.deleteFile(path);
  var pcLog = await syncLog(
    client: client,
    deviceId: 'pc',
    pathPrefix: _prefix,
    localLog: _log('a', 'from-pc', 'node-pc'),
    encode: _encode,
    decode: _decode,
    stateStore: storePc,
  );
  final pushed = await client.getFileText(path);
  _check('the log landed in the database', pushed != null);
  final revs = await client.getStringMap('_smoketest/revs');
  _check('a revision was published for this device',
      revs['pc'] == revisionOf(_encode(pcLog)), '${revs.keys}');

  stdout.writeln('\n== sync: an unchanged tick writes nothing ==');
  final before = await client.getStringMap('_smoketest/revs');
  pcLog = await syncLog(
    client: client,
    deviceId: 'pc',
    pathPrefix: _prefix,
    localLog: pcLog,
    encode: _encode,
    decode: _decode,
    stateStore: storePc,
  );
  _check('revision unchanged, so nothing was re-uploaded',
      (await client.getStringMap('_smoketest/revs'))['pc'] == before['pc']);

  stdout.writeln('\n== sync: two devices converge ==');
  final storePhone = InMemorySyncStateStore();
  final phoneLog = await syncLog(
    client: client,
    deviceId: 'phone',
    pathPrefix: _prefix,
    localLog: _log('b', 'from-phone', 'node-phone'),
    encode: _encode,
    decode: _decode,
    stateStore: storePhone,
  );
  _check('phone merged the pc record', phoneLog.containsKey('a'));
  final pcAfter = await syncLog(
    client: client,
    deviceId: 'pc',
    pathPrefix: _prefix,
    localLog: pcLog,
    encode: _encode,
    decode: _decode,
    stateStore: storePc,
  );
  _check('pc merged the phone record', pcAfter.containsKey('b'));
  _check('each device wrote only its own revision key',
      (await client.getStringMap('_smoketest/revs')).length == 2);

  stdout.writeln('\n== fail-closed ==');
  await auth.signOut();
  var threw = false;
  try {
    await client.getFileText(path);
  } on RemoteSyncError {
    threw = true;
  }
  _check('a revoked session fails loudly rather than returning null', threw);

  stdout.writeln('\n== cleanup ==');
  await auth.signIn(email: email, password: password);
  for (final device in ['pc', 'phone']) {
    await client.deleteFile('$_prefix/$device/log.json');
    await client.deleteFile('_smoketest/revs/$device');
  }
  final leftover = await client.listDirectory('_smoketest');
  _check('smoke-test data removed', leftover.isEmpty, '$leftover');

  client.close();
  auth.close();
  stdout.writeln(
    _failures == 0 ? '\nALL LIVE CHECKS PASSED' : '\n$_failures LIVE CHECK(S) FAILED',
  );
  exit(_failures == 0 ? 0 : 1);
}
