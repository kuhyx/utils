import 'dart:convert';

import 'package:data_transfer_flutter/data_transfer_flutter.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_platform.dart';

void main() {
  late FakePlatform fake;
  late DataTransferPlatform original;

  setUp(() {
    original = DataTransfer.platform;
    fake = FakePlatform();
    DataTransfer.platform = fake;
  });

  tearDown(() => DataTransfer.platform = original);

  group('exportJson', () {
    test('saves the map as indented JSON under the given name', () async {
      final saved = await exportJson(fileName: 'a.json', json: {'k': 1});

      expect(saved, isTrue);
      expect(fake.saves.single.$1, 'a.json');
      expect(
        fake.saves.single.$2,
        const JsonEncoder.withIndent('  ').convert({'k': 1}),
      );
      expect(fake.shares, isEmpty);
    });

    test('returns false when the dialog was cancelled', () async {
      fake.accept = false;

      expect(await exportJson(fileName: 'a.json', json: {}), isFalse);
    });
  });

  group('exportJsonText', () {
    test('passes an already-encoded string through untouched', () async {
      await exportJsonText(fileName: 'b.json', text: '{"x":1}');

      expect(fake.saves.single, ('b.json', '{"x":1}'));
    });
  });

  group('shareJson', () {
    test('uses the share action, not save', () async {
      final shared = await shareJson(fileName: 'c.json', json: {'k': 2});

      expect(shared, isTrue);
      expect(fake.shares.single.$1, 'c.json');
      expect(jsonDecode(fake.shares.single.$2), {'k': 2});
      expect(fake.saves, isEmpty);
    });
  });

  group('pickJson', () {
    test('decodes the picked file', () async {
      fake.picked = '{"a":[1,2]}';

      expect(await pickJson(), {
        'a': [1, 2],
      });
    });

    test('returns null when the picker was cancelled', () async {
      expect(await pickJson(), isNull);
      expect(await pickJsonText(), isNull);
    });

    test('rejects a file that is not JSON', () async {
      fake.picked = '{oops';

      await expectLater(pickJson, throwsA(isA<EnvelopeInvalidJson>()));
    });

    test('rejects JSON that is not an object', () async {
      fake.picked = '[1]';

      await expectLater(pickJson, throwsA(isA<EnvelopeNotObject>()));
    });
  });

  group('pickJsonText', () {
    test('returns the raw text without decoding it', () async {
      fake.picked = 'not even json';

      expect(await pickJsonText(), 'not even json');
    });
  });
}
