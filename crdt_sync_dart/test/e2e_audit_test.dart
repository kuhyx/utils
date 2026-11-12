/// The done check: find plaintext blobs in a raw RTDB dump.
///
/// RTDB returns each blob as a JSON string, so its quotes arrive escaped and
/// `grep -c '"title"'` prints 0 even on plaintext. The audit decodes instead.
library;

import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:test/test.dart';

// Shape copied from a live `GET /<root>.json` (scratch data).
const _livePlaintextDump =
    r'{"notes":{"pc":{"log~2Ejson":"{\"n2\":{\"id\":\"n2\",\"fields\":'
    r'{\"title\":[\"call mum\",\"1970-01-01T00:00:01.001Z-0000-pc\"]},'
    r'\"deleted\":false,\"deleted_hlc\":null}}"}},"revs":{"pc":"ab12"}}';

void main() {
  test('the grep done check misses live plaintext; the audit does not', () {
    expect('"title"'.allMatches(_livePlaintextDump), isEmpty);
    expect(plaintextBlobPaths(jsonDecode(_livePlaintextDump)), [
      'notes/pc/log.json',
    ]);
  });

  test('sealed blobs, revs and the clear e2e header pass', () async {
    final sealed = await E2eCipher(
      List<int>.filled(32, 1),
    ).seal('{"title":"x"}', path: 'notes/pc/log.json');
    final dump = {
      'e2e': '{"v":1,"kdf":"argon2id"}',
      'notes': {
        'pc': {'log~2Ejson': sealed},
      },
      'revs': {'pc': 'ab12'},
    };
    expect(plaintextBlobPaths(dump), isEmpty);
  });

  test('every plaintext leaf is reported, with keys unescaped', () {
    final dump = {
      'a': {
        'x~2Ey': '[1]',
        'b': {'c': ' {"k":1}'},
      },
      'n': 3,
      'nil': null,
    };
    expect(plaintextBlobPaths(dump), unorderedEquals(['a/x.y', 'a/b/c']));
  });

  test('a root that is itself plaintext, or empty, is handled', () {
    expect(plaintextBlobPaths('{"a":1}'), ['']);
    expect(plaintextBlobPaths(null), isEmpty);
  });
}
