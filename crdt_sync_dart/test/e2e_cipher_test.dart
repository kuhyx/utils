/// The record-blob AEAD: what makes the remote a blind relay.
library;

import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:glados/glados.dart' hide expect, group, test, setUp;
import 'package:test/test.dart';

const _path = 'todo-sync/notes/phone/log.json';

E2eCipher _cipher([int fill = 7, bool acceptPlaintext = true]) =>
    E2eCipher(List<int>.filled(32, fill), acceptPlaintext: acceptPlaintext);

void main() {
  Glados(any.letterOrDigits, ExploreConfig(numRuns: 60)).test(
    'open(seal(x)) == x for any text',
    (text) async {
      final cipher = _cipher();
      final sealed = await cipher.seal('{"t":"$text"}', path: _path);
      expect(await cipher.open(sealed, path: _path), '{"t":"$text"}');
    },
  );

  test('sealed text contains no plaintext and is not JSON', () async {
    final sealed = await _cipher().seal('{"title":"secret"}', path: _path);
    expect(sealed, isNot(contains('title')));
    expect(sealed, isNot(contains('secret')));
    expect(() => jsonDecode(sealed), throwsFormatException);
    expect(E2eCipher.isPlaintext(sealed), isFalse);
  });

  test('two seals of the same text differ (random nonce)', () async {
    final cipher = _cipher();
    expect(
      await cipher.seal('{}', path: _path),
      isNot(await cipher.seal('{}', path: _path)),
    );
  });

  test('wire format starts with the version byte', () async {
    final bytes = base64.decode(await _cipher().seal('{}', path: _path));
    expect(bytes.first, e2eFormatVersion);
    expect(bytes.length, 1 + 24 + 2 + 16);
  });

  test('plaintext JSON passes through during migration', () async {
    expect(await _cipher().open(' {"a":1}', path: _path), ' {"a":1}');
    expect(await _cipher().open('[1]', path: _path), '[1]');
    expect(E2eCipher.isPlaintext('\n{'), isTrue);
  });

  test('plaintext is refused once migration is over', () async {
    expect(
      () => _cipher(7, false).open('{"a":1}', path: _path),
      throwsA(isA<E2eDecryptError>()),
    );
  });

  group('rejects, as a FormatException so syncLog skips the peer', () {
    test('a wrong key', () async {
      final sealed = await _cipher(1).seal('{}', path: _path);
      expect(
        () => _cipher(2).open(sealed, path: _path),
        throwsA(isA<FormatException>()),
      );
    });

    test('a blob moved to another path', () async {
      final sealed = await _cipher().seal('{}', path: _path);
      expect(
        () => _cipher().open(sealed, path: 'todo-sync/notes/pc/log.json'),
        throwsA(isA<E2eDecryptError>()),
      );
    });

    test('a flipped ciphertext byte', () async {
      final bytes = base64.decode(await _cipher().seal('{}', path: _path));
      bytes[30] ^= 1;
      expect(
        () => _cipher().open(base64.encode(bytes), path: _path),
        throwsA(isA<E2eDecryptError>()),
      );
    });

    test('an unknown version byte', () async {
      final bytes = base64.decode(await _cipher().seal('{}', path: _path));
      bytes[0] = 9;
      expect(
        () => _cipher().open(base64.encode(bytes), path: _path),
        throwsA(
          isA<E2eDecryptError>().having(
            (e) => e.message,
            'message',
            contains('update the app'),
          ),
        ),
      );
    });

    test('text that is not base64', () {
      expect(
        () => _cipher().open('not base64 !!', path: _path),
        throwsA(isA<E2eDecryptError>()),
      );
    });

    test('a blob too short to hold nonce and tag', () {
      expect(
        () => _cipher().open(base64.encode([1, 2, 3]), path: _path),
        throwsA(isA<E2eDecryptError>()),
      );
    });

    test('an empty blob', () {
      expect(
        () => _cipher().open('', path: _path),
        throwsA(isA<E2eDecryptError>()),
      );
    });
  });

  test('a key that is not 32 bytes is a programming error', () {
    expect(() => E2eCipher(const [1, 2]), throwsArgumentError);
  });

  test('E2eDecryptError reads as itself', () {
    expect(E2eDecryptError('x').toString(), 'E2eDecryptError: x');
  });
}
