import 'dart:convert';
import 'dart:math';

import 'package:cryptography/cryptography.dart';

import 'e2e_cipher.dart';
import 'encrypting_store.dart';
import 'remote_store.dart';

const _saltLength = 16;
const _headerVersion = 1;

/// Argon2id cost, stored in the header so it can be raised later.
class Argon2Params {
  const Argon2Params({
    required this.memoryKiB,
    required this.iterations,
    required this.parallelism,
  });

  /// OWASP's floor (19 MiB, t=2); higher stalls the Flutter-web desktop build.
  static const recommended = Argon2Params(
    memoryKiB: 19456,
    iterations: 2,
    parallelism: 1,
  );

  final int memoryKiB;
  final int iterations;
  final int parallelism;
}

class E2eHeaderError extends FormatException {
  E2eHeaderError(super.message);

  @override
  String toString() => 'E2eHeaderError: $message';
}

class E2eWrongPassphraseError implements Exception {
  @override
  String toString() => 'E2eWrongPassphraseError: wrong sync passphrase';
}

/// The clear header's path: a sibling of the device dirs, like `revs`.
String defaultE2ePath(String pathPrefix) {
  final cut = pathPrefix.lastIndexOf('/');
  return cut < 0 ? '$pathPrefix/e2e' : '${pathPrefix.substring(0, cut)}/e2e';
}

class _Header {
  _Header(this.salt, this.params, this.check);

  factory _Header.parse(String text) {
    final Object? json;
    try {
      json = jsonDecode(text);
    } on FormatException {
      throw E2eHeaderError('e2e header is not JSON');
    }
    if (json is! Map<String, dynamic>) {
      throw E2eHeaderError('e2e header is not an object');
    }
    if (json['v'] != _headerVersion) {
      throw E2eHeaderError('e2e header v${json['v']}; update the app');
    }
    try {
      if (json['kdf'] != 'argon2id') throw const FormatException();
      return _Header(
        base64.decode(json['salt'] as String),
        Argon2Params(
          memoryKiB: json['m'] as int,
          iterations: json['t'] as int,
          parallelism: json['p'] as int,
        ),
        json['check'] as String,
      );
    } on Object {
      throw E2eHeaderError('e2e header is malformed');
    }
  }

  final List<int> salt;
  final Argon2Params params;
  final String check;

  String encode() => jsonEncode({
    'v': _headerVersion,
    'kdf': 'argon2id',
    'salt': base64.encode(salt),
    'm': params.memoryKiB,
    't': params.iterations,
    'p': params.parallelism,
    'check': check,
  });
}

/// A 32-byte master key plus its HKDF subkeys for sealing, revisions and the
/// passphrase check. Cache [bytes] in the OS keystore, never in RTDB.
class E2eKey {
  E2eKey._(this.bytes, this._enc, this._rev, this._check);

  static Future<E2eKey> fromBytes(List<int> bytes) {
    if (bytes.length != 32) {
      throw ArgumentError.value(bytes.length, 'bytes', 'must be 32 bytes');
    }
    return _expand(List<int>.unmodifiable(bytes));
  }

  static Future<E2eKey> _expand(List<int> master) async {
    Future<List<int>> sub(String label) async {
      final key = await Hkdf(hmac: Hmac.sha256(), outputLength: 32).deriveKey(
        secretKey: SecretKey(master),
        info: utf8.encode('crdt_sync e2e $label'),
      );
      return key.bytes;
    }

    return E2eKey._(
      master,
      await sub('enc'),
      SecretKey(await sub('rev')),
      SecretKey(await sub('check')),
    );
  }

  final List<int> bytes;
  final List<int> _enc;
  final SecretKey _rev;
  final SecretKey _check;

  E2eCipher cipher({bool acceptPlaintext = true}) =>
      E2eCipher(_enc, acceptPlaintext: acceptPlaintext);

  /// Keyed `revisionOf`: a published revision cannot confirm a guessed log.
  Future<String> revision(String text) async {
    final mac = await Hmac.sha256().calculateMac(
      utf8.encode(text),
      secretKey: _rev,
    );
    return mac.bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
  }

  Future<String> _checkFor(List<int> salt) async {
    final mac = await Hmac.sha256().calculateMac(salt, secretKey: _check);
    return base64.encode(mac.bytes);
  }
}

Future<E2eKey> _derive(
  String passphrase,
  List<int> salt,
  Argon2Params params,
) async {
  final key = await Argon2id(
    parallelism: params.parallelism,
    memory: params.memoryKiB,
    iterations: params.iterations,
    hashLength: 32,
  ).deriveKeyFromPassword(password: passphrase, nonce: salt);
  return E2eKey._expand(await key.extractBytes());
}

Future<_Header?> _readHeader(RemoteStore store, String path) async {
  final text = await store.getFileText(path);
  return text == null ? null : _Header.parse(text);
}

/// Derives this app's key from [passphrase], creating the header on first use.
///
/// Throws [E2eWrongPassphraseError] on a failed check and [E2eHeaderError]
/// for an unreadable header, which is never overwritten.
Future<E2eKey> unlockE2e({
  required RemoteStore store,
  required String pathPrefix,
  required String passphrase,
  Argon2Params params = Argon2Params.recommended,
  Random? random,
  String? e2ePath,
}) async {
  if (passphrase.isEmpty) {
    throw ArgumentError.value('', 'passphrase', 'must not be empty');
  }
  final path = e2ePath ?? defaultE2ePath(pathPrefix);
  var header = await _readHeader(store, path);
  if (header == null) {
    final rng = random ?? Random.secure();
    final salt = List<int>.generate(_saltLength, (_) => rng.nextInt(256));
    final key = await _derive(passphrase, salt, params);
    final encoded = _Header(salt, params, await key._checkFor(salt)).encode();
    await store.putFileText(path, encoded, message: path);
    // Two devices setting up at once: the last write wins, so re-read.
    final stored = await store.getFileText(path) ?? encoded;
    if (stored == encoded) return key;
    header = _Header.parse(stored);
  }
  final key = await _derive(passphrase, header.salt, header.params);
  if (await key._checkFor(header.salt) != header.check) {
    throw E2eWrongPassphraseError();
  }
  return key;
}

sealed class E2eState {}

/// No header and no key: this app has never been encrypted.
final class E2eOff extends E2eState {}

enum E2eLockReason { needsPassphrase, wrongKey, badHeader }

/// Encryption is on, but this device must not sync until it has the key.
final class E2eLocked extends E2eState {
  E2eLocked(this.reason);

  final E2eLockReason reason;
}

final class E2eReady extends E2eState {
  E2eReady(this.store);

  final EncryptingStore store;
}

Future<E2eState> openE2e({
  required RemoteStore store,
  required String pathPrefix,
  E2eKey? key,
  String? e2ePath,
  String? revsPath,
  bool acceptPlaintext = true,
}) async {
  final _Header? header;
  try {
    header = await _readHeader(store, e2ePath ?? defaultE2ePath(pathPrefix));
  } on E2eHeaderError {
    return E2eLocked(E2eLockReason.badHeader);
  }
  if (key == null) {
    return header == null ? E2eOff() : E2eLocked(E2eLockReason.needsPassphrase);
  }
  if (header == null || await key._checkFor(header.salt) != header.check) {
    return E2eLocked(E2eLockReason.wrongKey);
  }
  return E2eReady(
    EncryptingStore(
      store,
      key,
      pathPrefix: pathPrefix,
      revsPath: revsPath,
      e2ePath: e2ePath,
      acceptPlaintext: acceptPlaintext,
    ),
  );
}
