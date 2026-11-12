/// Per-record envelope: ids and HLCs stay clear, field names and values are
/// opaque, and merge results are identical with and without encryption.
library;

import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:glados/glados.dart' hide expect, group, test, setUp;
import 'package:test/test.dart';

import 'e2e_fakes.dart';

const _path = 'app/notes-e2e/phone/log.json';

E2eCipher _cipher([int fill = 7, bool acceptPlaintext = true]) =>
    E2eCipher(List<int>.filled(32, fill), acceptPlaintext: acceptPlaintext);

Hlc _hlc(int ms, int counter, String node) =>
    Hlc(wallTimeMs: ms, counter: counter, nodeId: node);

Log _logFrom(List<(int, int, String)> rows) {
  final log = <String, Record>{};
  for (final (id, field, value) in rows) {
    final key = 'r$id';
    final old = log[key];
    log[key] = Record(
      id: key,
      fields: {
        ...?old?.fields,
        'f$field': (value, _hlc(1000 + id * 7 + field, field, 'n$id')),
      },
      deleted: id % 4 == 0,
      deletedHlc: id % 4 == 0 ? _hlc(5000, 0, 'n$id') : null,
    );
  }
  return log;
}

final _rows = any.list(
  any.combine3(
    any.intInRange(0, 6),
    any.intInRange(0, 4),
    any.letterOrDigits,
    (a, b, c) => (a, b, c),
  ),
);

void main() {
  Glados(_rows, ExploreConfig(numRuns: 40)).test(
    'decode(open(seal(encode(log)))) == log',
    (rows) async {
      final log = _logFrom(rows);
      final cipher = _cipher();
      final sealed = await sealLogText(encodeLog(log), cipher, path: _path);
      final opened = await openLogText(sealed, cipher, path: _path);
      expect(encodeLog(decodeLog(opened)), encodeLog(log));
    },
  );

  Glados2(_rows, _rows, ExploreConfig(numRuns: 40)).test(
    'merge through the envelope == merge without it',
    (a, b) async {
      final cipher = _cipher();
      Future<Log> viaCipher(Log log) async => decodeLog(
        await openLogText(
          await sealLogText(encodeLog(log), cipher, path: _path),
          cipher,
          path: _path,
        ),
      );
      final la = _logFrom(a);
      final lb = _logFrom(b);
      final plain = mergeLogs(la, lb);
      final sealed = mergeLogs(await viaCipher(la), await viaCipher(lb));
      expect(encodeLog(sealed), encodeLog(plain));
    },
  );

  test('ids and HLCs are clear, names and values are not', () async {
    final log = logOf({'n1': 'buy milk'});
    final sealed = await sealLogText(encodeLog(log), _cipher(), path: _path);
    final json = jsonDecode(sealed) as Map<String, dynamic>;
    expect(json['v'], 1);
    final rec = (json['r'] as Map<String, dynamic>)['n1'] as Map;
    expect(rec['h'], log['n1']!.fields['title']!.$2.toStr());
    expect(rec['d'], false);
    expect(sealed, isNot(contains('title')));
    expect(sealed, isNot(contains('buy milk')));
    expect(isE2eEnvelope(sealed), isTrue);
    expect(isE2eEnvelope(encodeLog(log)), isFalse);
  });

  test('legacy plaintext passes only while acceptPlaintext', () async {
    final text = encodeLog(logOf({'n1': 'x'}));
    expect(await openLogText(text, _cipher(), path: _path), text);
    expect(
      () => openLogText(text, _cipher(7, false), path: _path),
      throwsA(isA<E2eDecryptError>()),
    );
  });

  test('a record id named v is still legacy plaintext', () async {
    final text = encodeLog(logOf({'v': 'x'}));
    expect(isE2eEnvelope(text), isFalse);
  });

  group('tamper and wrong key are E2eDecryptError', () {
    Future<String> sealed() async =>
        sealLogText(encodeLog(logOf({'n1': 'x'})), _cipher(), path: _path);

    test('wrong key', () async {
      final text = await sealed();
      expect(
        () => openLogText(text, _cipher(8), path: _path),
        throwsA(isA<E2eDecryptError>()),
      );
    });
    test('moved path', () async {
      final text = await sealed();
      expect(
        () => openLogText(text, _cipher(), path: '$_path-x'),
        throwsA(isA<E2eDecryptError>()),
      );
    });
    test('flipped clear deleted flag', () async {
      final json = jsonDecode(await sealed()) as Map<String, dynamic>;
      ((json['r'] as Map)['n1'] as Map)['d'] = true;
      expect(
        () => openLogText(jsonEncode(json), _cipher(), path: _path),
        throwsA(isA<E2eDecryptError>()),
      );
    });
    test('record swapped to another id', () async {
      final json = jsonDecode(await sealed()) as Map<String, dynamic>;
      final r = json['r'] as Map;
      r['n2'] = r.remove('n1');
      expect(
        () => openLogText(jsonEncode(json), _cipher(), path: _path),
        throwsA(isA<E2eDecryptError>()),
      );
    });
    test('mis-shaped envelope', () async {
      expect(
        () => openLogText('{"v":1,"r":5}', _cipher(), path: _path),
        throwsA(isA<E2eDecryptError>()),
      );
    });
  });

  test('text that is not a log is sealed whole and opens back', () async {
    final cipher = _cipher();
    final sealed = await sealLogText('{"n":{"id":1}}', cipher, path: _path);
    expect(sealed, isNot(contains('"id"')));
    expect(await openLogText(sealed, cipher, path: _path), '{"n":{"id":1}}');
  });
}
