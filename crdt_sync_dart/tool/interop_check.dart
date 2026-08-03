/// Live cross-language check: reads what the Python client wrote, merges a
/// Dart-side record, and confirms both survive. The two implementations must
/// agree byte-for-byte or a phone on Dart would not see a PC on Python.
library;

import 'dart:convert';
import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';

/// Environment-specific values (project, account, database URL) live here,
/// mode 0600 -- never in source, because this repository is public.
final _configDir = '${Platform.environment['HOME']}/.config/crdt-sync';

Log _decode(String t) => (jsonDecode(t) as Map<String, dynamic>)
    .map((k, v) => MapEntry(k, Record.fromJson(v as Map<String, dynamic>)));
String _encode(Log l) =>
    jsonEncode(l.map((k, v) => MapEntry(k, v.toJson())));

Future<void> main(List<String> args) async {
  final cfg = jsonDecode(
    File('$_configDir/firebase.json').readAsStringSync(),
  ) as Map<String, dynamic>;
  final auth = FirebaseTokenProvider(
    apiKey: cfg['apiKey'] as String,
    store: InMemoryCredentialStore(),
  );
  await auth.signIn(
    email: cfg['email'] as String,
    password: File('$_configDir/password').readAsStringSync(),
  );
  final client = FirebaseRestClient(
    databaseUrl: cfg['databaseUrl'] as String,
    auth: auth,
  );

  final merged = await syncLog(
    client: client,
    deviceId: 'dartdev',
    pathPrefix: '_interop/devices',
    localLog: {
      'dart-rec': Record(
        id: 'dart-rec',
        fields: {
          'value': (
            'written-by-dart',
            Hlc(wallTimeMs: 1000, counter: 0, nodeId: 'node-dart'),
          ),
        },
      ),
    },
    encode: _encode,
    decode: _decode,
    stateStore: InMemorySyncStateStore(),
  );

  final ok = merged.containsKey('py-rec') && merged.containsKey('dart-rec');
  stdout.writeln('dart sees records: ${merged.keys.toList()}');
  stdout.writeln(
    'python record value: ${merged['py-rec']?.fields['value']?.$1}',
  );
  stdout.writeln('revs: ${await client.getStringMap('_interop/revs')}');

  // Clean up both devices' data.
  for (final d in ['pydev', 'dartdev']) {
    await client.deleteFile('_interop/devices/$d/log.json');
    await client.deleteFile('_interop/revs/$d');
  }
  stdout.writeln(ok ? '\nINTEROP OK' : '\nINTEROP FAILED');
  exit(ok ? 0 : 1);
}
