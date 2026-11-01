import 'dart:convert';

import 'package:data_transfer_flutter/data_transfer_flutter.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final now = DateTime.utc(2026, 11, 1, 12, 30);

  group('buildEnvelope', () {
    test('puts format, version and a UTC timestamp first', () {
      final envelope = buildEnvelope(
        format: 'demo_export',
        version: 2,
        now: now,
        body: {
          'items': <Object?>[1, 2],
        },
      );

      expect(envelope.keys, ['format', 'version', 'exported_at', 'items']);
      expect(envelope['format'], 'demo_export');
      expect(envelope['version'], 2);
      expect(envelope['exported_at'], '2026-11-01T12:30:00.000Z');
      expect(envelope['items'], [1, 2]);
    });

    test('converts a local clock to UTC', () {
      final local = DateTime.parse('2026-11-01T12:30:00+02:00');

      final envelope = buildEnvelope(format: 'f', version: 1, now: local);

      expect(envelope['exported_at'], '2026-11-01T10:30:00.000Z');
    });

    test('refuses a body that shadows an envelope key', () {
      expect(
        () => buildEnvelope(
          format: 'f',
          version: 1,
          now: now,
          body: {'version': 9},
        ),
        throwsArgumentError,
      );
    });
  });

  group('validateEnvelope', () {
    final good = <String, Object?>{
      'format': 'demo_export',
      'version': 1,
      'exported_at': 'x',
      'rest': true,
    };

    test('returns the same map when format and version match', () {
      final out = validateEnvelope(good, format: 'demo_export', version: 1);

      expect(out, same(good));
    });

    test('rejects a non-object as not an object', () {
      for (final value in <Object?>[null, 3, 'text', <Object?>[]]) {
        expect(
          () => validateEnvelope(value, format: 'demo_export', version: 1),
          throwsA(isA<EnvelopeNotObject>()),
        );
      }
    });

    test('rejects a foreign format and reports both names', () {
      expect(
        () => validateEnvelope(
          {...good, 'format': 'other'},
          format: 'demo_export',
          version: 1,
        ),
        throwsA(
          isA<EnvelopeFormatMismatch>()
              .having((e) => e.expected, 'expected', 'demo_export')
              .having((e) => e.actual, 'actual', 'other')
              .having((e) => e.message, 'message', contains('demo_export')),
        ),
      );
    });

    test('rejects a missing format', () {
      expect(
        () =>
            validateEnvelope({'version': 1}, format: 'demo_export', version: 1),
        throwsA(isA<EnvelopeFormatMismatch>()),
      );
    });

    test('rejects another version and reports both numbers', () {
      expect(
        () => validateEnvelope(
          {...good, 'version': 7},
          format: 'demo_export',
          version: 1,
        ),
        throwsA(
          isA<EnvelopeVersionMismatch>()
              .having((e) => e.expected, 'expected', 1)
              .having((e) => e.actual, 'actual', 7)
              .having((e) => e.message, 'message', contains('7')),
        ),
      );
    });

    test('rejects a missing version', () {
      expect(
        () => validateEnvelope(
          {'format': 'demo_export'},
          format: 'demo_export',
          version: 1,
        ),
        throwsA(isA<EnvelopeVersionMismatch>()),
      );
    });

    test('every error is a FormatException', () {
      expect(
        () => validateEnvelope(null, format: 'f', version: 1),
        throwsFormatException,
      );
      expect(
        () => validateEnvelope({'format': 'g'}, format: 'f', version: 1),
        throwsFormatException,
      );
      expect(
        () => validateEnvelope(
          {'format': 'f', 'version': 2},
          format: 'f',
          version: 1,
        ),
        throwsFormatException,
      );
    });
  });

  group('EnvelopeException', () {
    test('behaves as a FormatException with no source position', () {
      const FormatException error = EnvelopeInvalidJson();

      expect(error.message, 'not valid JSON');
      expect(error.source, isNull);
      expect(error.offset, isNull);
      expect(error.toString(), contains('not valid JSON'));
    });
  });

  group('parseEnvelope', () {
    test('round-trips what buildEnvelope produced', () {
      final text = jsonEncode(
        buildEnvelope(format: 'f', version: 1, now: now, body: {'n': 1}),
      );

      final parsed = parseEnvelope(text, format: 'f', version: 1);

      expect(parsed['n'], 1);
    });

    test('reports malformed JSON as an invalid-JSON error', () {
      expect(
        () => parseEnvelope('{oops', format: 'f', version: 1),
        throwsA(isA<EnvelopeInvalidJson>()),
      );
    });

    test('runs the format and version checks on valid JSON', () {
      expect(
        () => parseEnvelope(
          '{"format":"g","version":1}',
          format: 'f',
          version: 1,
        ),
        throwsA(isA<EnvelopeFormatMismatch>()),
      );
    });
  });
}
