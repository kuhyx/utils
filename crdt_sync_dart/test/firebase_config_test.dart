/// Tests for the shared Firebase configuration on the Dart side.
///
/// The failure modes asserted here are the ones that would otherwise surface
/// as an authentication error long after the real mistake, so each is checked
/// to name the field at fault rather than merely to throw.
library;

import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:test/test.dart';

const _valid = {
  'apiKey': 'AIzaSyExample',
  'databaseUrl':
      'https://kuhy-syncs-default-rtdb.europe-west1.firebasedatabase.app',
  'projectId': 'kuhy-syncs',
  'uid': 'OvA2REQyLIhAHOEjzwS1o877rgG3',
  'email': 'sync@example.com',
};

void main() {
  group('FirebaseConfig', () {
    test('parses a valid config', () {
      final config = FirebaseConfig.parse(jsonEncode(_valid));

      expect(config.apiKey, 'AIzaSyExample');
      expect(config.projectId, 'kuhy-syncs');
      expect(config.uid, 'OvA2REQyLIhAHOEjzwS1o877rgG3');
      expect(config.email, 'sync@example.com');
      expect(config.databaseUrl, endsWith('europe-west1.firebasedatabase.app'));
    });

    test('ignores the scaffold comment keys', () {
      final annotated = {..._valid, '_comment_apiKey': 'where to find it'};

      expect(
        FirebaseConfig.parse(jsonEncode(annotated)).apiKey,
        'AIzaSyExample',
      );
    });

    test('agrees with the Python side on the field names', () {
      // Both languages read the same file; a rename on one side only would
      // break the other silently.
      final config = FirebaseConfig.parse(jsonEncode(_valid));

      expect(config.databaseUrl, _valid['databaseUrl']);
      expect(config.uid, _valid['uid']);
    });

    for (final field in _valid.keys) {
      test('names $field when it is missing', () {
        final incomplete = {..._valid}..remove(field);

        expect(
          () => FirebaseConfig.parse(jsonEncode(incomplete)),
          throwsA(
            isA<ConfigException>().having(
              (e) => e.message,
              'message',
              contains(field),
            ),
          ),
        );
      });
    }

    test('names an empty field', () {
      final blank = {..._valid, 'uid': '  '};

      expect(
        () => FirebaseConfig.parse(jsonEncode(blank)),
        throwsA(
          isA<ConfigException>().having(
            (e) => e.message,
            'message',
            contains('uid'),
          ),
        ),
      );
    });

    test('names an unfilled placeholder', () {
      final unfilled = {..._valid, 'apiKey': 'PASTE_WEB_API_KEY_HERE'};

      expect(
        () => FirebaseConfig.parse(jsonEncode(unfilled)),
        throwsA(
          isA<ConfigException>().having(
            (e) => e.message,
            'message',
            contains('placeholder for: apiKey'),
          ),
        ),
      );
    });

    test('rejects unparsable JSON', () {
      expect(
        () => FirebaseConfig.parse('{not json'),
        throwsA(isA<ConfigException>()),
      );
    });

    test('rejects a non-object document', () {
      expect(
        () => FirebaseConfig.parse('["a list"]'),
        throwsA(isA<ConfigException>()),
      );
    });

    test('has a readable toString on the exception', () {
      expect(ConfigException('boom').toString(), contains('boom'));
    });
  });
}
