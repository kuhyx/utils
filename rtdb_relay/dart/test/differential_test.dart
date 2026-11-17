// Old vs new: the tutor's pre-extraction sealer (frozen copy) and the
// package's RelaySealer over the tutor layout must agree byte for byte, or
// the APK already on the phone stops reading what the new code writes.
import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:crdt_sync/crdt_sync.dart' show E2eCipher;
import 'package:flutter_test/flutter_test.dart';
import 'package:rtdb_relay/src/layout.dart';
import 'package:rtdb_relay/src/sealer.dart';

import 'support/legacy_tutor_seal.dart' as old;
import 'support/tutor_layout.dart';

const _segments = [
  'requests',
  'req',
  'result',
  'claim',
  'presence',
  'workers',
  'clients',
  'sessions',
  'meta',
  'msgs',
  'receipts',
  'user',
  'progress',
  'steps',
  'rid',
  'subjects',
  'plan',
  'cards',
  'concepts',
  'log',
  'feedback',
  'uploads',
  'live',
  'prefs',
  'stats',
  'rev',
  'migration',
  'session_index',
  'x',
  '1',
];

List<String> _path(Random rng) => [
  for (var i = 0, n = rng.nextInt(6); i < n; i++)
    _segments[rng.nextInt(_segments.length)],
];

/// A sealable value for the unit at [parts]: a map holding its clear fields.
Object? _value(Random rng, Set<String> keep) => {
  'n': rng.nextInt(1000),
  'text': 'v${rng.nextInt(99)}',
  for (final k in keep) k: rng.nextInt(1 << 30),
};

void main() {
  final cipher = E2eCipher(
    Uint8List.fromList(List.generate(32, (i) => i * 7 % 256)),
  );
  final before = old.TutorSealer(cipher);
  final after = RelaySealer(cipher, layout: tutorLayout);

  test('same root and the same rule for 20000 random paths', () {
    expect(tutorLayout.root, old.kE2eLayout.prefix);
    final rng = Random(20261117);
    for (var i = 0; i < 20000; i++) {
      final parts = _path(rng);
      final a = old.classifyE2e(parts);
      final b = tutorLayout.classify(parts);
      expect(
        [b.kind.name, b.depth, b.keep],
        [a.kind.name, a.depth, a.keep],
        reason: parts.join('/'),
      );
      expect(
        tutorLayout.unitPath(parts.join('/')),
        old.e2eUnitPath(parts.join('/')),
      );
    }
  });

  test(
    'a unit sealed by either side opens on the other, identically',
    () async {
      final rng = Random(7);
      var units = 0;
      for (var i = 0; i < 40000 && units < 300; i++) {
        final parts = _path(rng);
        final rule = tutorLayout.classify(parts);
        if (rule.kind != E2eRuleKind.unit) continue;
        units++;
        final rel = parts.join('/');
        final value = _value(rng, rule.keep);
        final sealedOld = await before.seal(rel, value);
        final sealedNew = await after.seal(rel, value);
        // Nonces differ; the clear siblings and the shape must not.
        String strip(Object? v) => jsonEncode({
          for (final e in (v! as Map).entries)
            if (e.key != kSealedKey) e.key: e.value,
        });
        expect(strip(sealedNew), strip(sealedOld));
        expect(await after.open(rel, sealedOld), value);
        expect(await before.open(rel, sealedNew), value);
      }
      expect(units, 300);
    },
  );
}
