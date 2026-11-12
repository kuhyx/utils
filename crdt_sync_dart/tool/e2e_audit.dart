/// Read-only done check: lists plaintext blobs under an RTDB root.
///
/// Usage: `dart run tool/e2e_audit.dart <root> <firebase_auth.json>`
/// Exit 0 when every blob is sealed, 1 when any is plaintext, 2 on misuse.
library;

import 'dart:convert';
import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:http/http.dart' as http;

Future<void> main(List<String> args) async {
  if (args.length != 2) {
    stderr.writeln('usage: e2e_audit.dart <root> <firebase_auth.json>');
    exit(2);
  }
  final [root, sessionFile] = args;
  final home = Platform.environment['HOME'];
  final cfg =
      jsonDecode(
            File('$home/.config/crdt-sync/firebase.json').readAsStringSync(),
          )
          as Map<String, dynamic>;
  final session = FirebaseCredentials.fromJson(
    jsonDecode(File(sessionFile).readAsStringSync()) as Map<String, dynamic>,
  );
  final auth = FirebaseTokenProvider(
    apiKey: cfg['apiKey'] as String,
    store: InMemoryCredentialStore(session),
  );
  final url = Uri.parse(
    '${cfg['databaseUrl']}/${encodePath(root)}.json'
    '?auth=${await auth.idToken()}',
  );
  final response = await http.get(url);
  if (response.statusCode != 200) {
    stderr.writeln('GET $root: HTTP ${response.statusCode}');
    exit(2);
  }
  final plaintext = plaintextBlobPaths(jsonDecode(response.body));
  stdout.writeln('plaintext blobs under $root: ${plaintext.length}');
  for (final path in plaintext) {
    stdout.writeln('  $root/$path');
  }
  exit(plaintext.isEmpty ? 0 : 1);
}
