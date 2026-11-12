/// Cross-language golden vectors: Dart opens what the Python port sealed.
library;

import 'dart:convert';
import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:test/test.dart';

import 'e2e_fakes.dart';

void main() {
  final vec =
      jsonDecode(File('test/fixtures/e2e_py_vectors.json').readAsStringSync())
          as Map<String, dynamic>;

  Future<E2eKey> key() => unlockE2e(
    store: MemoryRemote({'vec/e2e': vec['header'] as String}),
    pathPrefix: 'vec/notes-e2e',
    passphrase: vec['passphrase'] as String,
    e2ePath: 'vec/e2e',
  );

  test('Argon2id and HKDF match Python', () async {
    final hex = (await key()).bytes
        .map((b) => b.toRadixString(16).padLeft(2, '0'))
        .join();
    expect(hex, vec['master_hex']);
  });

  test('opens a Python envelope and whole blob', () async {
    final cipher = (await key()).cipher();
    final path = vec['path'] as String;
    final opened = await openLogText(
      vec['envelope'] as String,
      cipher,
      path: path,
    );
    expect(jsonDecode(opened), jsonDecode(vec['log'] as String));
    expect(
      await openLogText(vec['whole'] as String, cipher, path: path),
      'not a log',
    );
  });
}
