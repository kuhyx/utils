import 'dart:convert';

import 'package:cryptography/cryptography.dart';

const int e2eFormatVersion = 1;

const _nonceLength = 24;
const _tagLength = 16;

/// A FormatException so `syncLog` skips the peer instead of aborting the tick.
class E2eDecryptError extends FormatException {
  E2eDecryptError(super.message);

  @override
  String toString() => 'E2eDecryptError: $message';
}

/// XChaCha20-Poly1305 per blob: base64 `[version][nonce][ct][tag]`, with the
/// version byte and remote path as AAD so blobs cannot be swapped.
///
/// [acceptPlaintext] reads un-migrated peers; turn it off after migration.
class E2eCipher {
  E2eCipher(List<int> key, {this.acceptPlaintext = true})
    : _key = SecretKey(List<int>.unmodifiable(key)) {
    if (key.length != 32) {
      throw ArgumentError.value(key.length, 'key', 'must be 32 bytes');
    }
  }

  final SecretKey _key;
  final bool acceptPlaintext;

  static final _aead = Xchacha20.poly1305Aead();

  static bool isPlaintext(String stored) {
    final trimmed = stored.trimLeft();
    return trimmed.startsWith('{') || trimmed.startsWith('[');
  }

  Future<String> seal(String plaintext, {required String path}) async {
    final box = await _aead.encrypt(
      utf8.encode(plaintext),
      secretKey: _key,
      nonce: _aead.newNonce(),
      aad: _aad(e2eFormatVersion, path),
    );
    return base64.encode([
      e2eFormatVersion,
      ...box.nonce,
      ...box.cipherText,
      ...box.mac.bytes,
    ]);
  }

  Future<String> open(String stored, {required String path}) async {
    if (isPlaintext(stored)) {
      if (acceptPlaintext) return stored;
      throw E2eDecryptError('plaintext blob at $path after migration');
    }
    final List<int> bytes;
    try {
      bytes = base64.decode(stored);
    } on FormatException {
      throw E2eDecryptError('blob at $path is neither JSON nor base64');
    }
    if (bytes.isEmpty) throw E2eDecryptError('empty blob at $path');
    final version = bytes.first;
    if (version != e2eFormatVersion) {
      throw E2eDecryptError(
        'blob at $path uses format $version; update the app to read it',
      );
    }
    if (bytes.length < 1 + _nonceLength + _tagLength) {
      throw E2eDecryptError('blob at $path is truncated');
    }
    final box = SecretBox(
      bytes.sublist(1 + _nonceLength, bytes.length - _tagLength),
      nonce: bytes.sublist(1, 1 + _nonceLength),
      mac: Mac(bytes.sublist(bytes.length - _tagLength)),
    );
    try {
      final clear = await _aead.decrypt(
        box,
        secretKey: _key,
        aad: _aad(version, path),
      );
      return utf8.decode(clear);
    } on SecretBoxAuthenticationError {
      throw E2eDecryptError('blob at $path failed authentication');
    }
  }

  static List<int> _aad(int version, String path) => [
    version,
    ...utf8.encode(path),
  ];
}
