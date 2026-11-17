import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:rtdb_relay/src/json_tree.dart';
import 'package:rtdb_relay/src/layout.dart';
import 'package:rtdb_relay/src/rtdb_client.dart';
import 'package:rtdb_relay/src/rtdb_event.dart';
import 'package:rtdb_relay/src/rtdb_stream.dart';

import 'support/e2e_fixture.dart';
import 'support/fake_rtdb.dart';
import 'support/tutor_layout.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'a pushed request is ciphertext at rest, read back in the clear',
    () async {
      final db = FakeRtdb();
      final client = sealedClient(db);
      final stored = await client.put('tutor/v1-e2e/requests/$testRid/req', {
        'kind': 'message',
        'dev': 'd1',
        'created': {'.sv': 'timestamp'},
        'body': {'session': '20261012-170448-5b71', 'text': 'secret words'},
      });
      final atRest = jsonEncode(db.root);
      expect(atRest, isNot(contains('secret words')));
      expect(atRest, isNot(contains('"text"')));
      expect(atRest, isNot(contains('"kind"')));
      // The server timestamp the credit maths needs stays clear and resolved.
      expect(
        getAt(db.root, '${'tutor/v1-e2e/requests/$testRid/req'}/created'),
        db.serverTime,
      );
      expect((stored! as Map)['body'], {
        'session': '20261012-170448-5b71',
        'text': 'secret words',
      });
      final read = await client.get('tutor/v1-e2e/requests/$testRid') as Map?;
      expect((read!['req'] as Map)['created'], db.serverTime);
      expect(((read['req'] as Map)['body'] as Map)['text'], 'secret words');
    },
  );

  test('the vectors pin the rules and open what Python sealed', () async {
    expect(e2eVectors['root'], tutorLayout.root);
    expect(e2eVectors['sealed_key'], kSealedKey);
    for (final r
        in (e2eVectors['rules'] as List).cast<Map<String, dynamic>>()) {
      expect(
        tutorLayout.classify(e2eParts(r['path'] as String)).kind.name,
        r['kind'],
        reason: r['path'] as String,
      );
    }
    final s = vectorSealer();
    for (final u
        in (e2eVectors['units'] as List).cast<Map<String, dynamic>>()) {
      final path = u['path'] as String;
      expect(await s.open(path, u['stored']), u['value'], reason: path);
      // And Dart's own seal round-trips through the same layout.
      expect(await s.open(path, await s.seal(path, u['value'])), u['value']);
    }
  });

  test('every path the app writes has a rule', () async {
    final s = vectorSealer();
    String rel(String p) => p.substring('tutor/v1-e2e'.length + 1);
    final writes = <String, Object?>{
      'tutor/v1-e2e/requests/$testRid/req': {'kind': 'x', 'created': 1},
      'tutor/v1-e2e/feedback/$testRid': {'text': 'x'},
      'tutor/v1-e2e/uploads/$testRid/c0001': 'aGVsbG8=',
      'tutor/v1-e2e/log/0b6f2c1e-8f2a-4c1d-9e3b-7a5d4c3b2a10/$testRid': {
        'r': 3,
      },
      'tutor/v1-e2e/prefs/current_subject': 'car',
      'tutor/v1-e2e/presence/clients/0b6f2c1e-8f2a-4c1d-9e3b-7a5d4c3b2a10': {
        'platform': 'web',
        'seen': 1,
      },
      'tutor/v1-e2e/sessions/20261012-170448-5b71/user': {'archived': true},
    };
    for (final e in writes.entries) {
      final sealed = await s.seal(rel(e.key), e.value);
      expect(jsonEncode(sealed), contains(kSealedKey), reason: e.key);
      expect(await s.open(rel(e.key), sealed), e.value, reason: e.key);
    }
    await expectLater(
      s.seal('secrets', {'a': 1}),
      throwsA(isA<E2eLayoutError>()),
    );
    await expectLater(
      s.sealPatch('sessions/s/msgs/m0001', {'text': 'x'}),
      throwsA(isA<E2eLayoutError>()),
    );
    await expectLater(
      s.open('stats/today/x', 1),
      throwsA(isA<E2eLayoutError>()),
    );
    expect(
      await s.open('prefs', {
        'current_subject': {kSealedKey: 'AQ=='},
        'other': 'legacy',
      }),
      {'other': 'legacy'},
    );
    expect(await s.open('sessions', [1]), [1]);
    expect(await s.seal('presence/clients/d', {'x': null}), isNull);
  });

  test('patch, tagged reads, below-unit reads and events open', () async {
    final db = FakeRtdb();
    final client = sealedClient(db);
    const session = 'tutor/v1-e2e/sessions/20261012-170448-5b71';
    await client.patch('$session/user', {'archived': true});
    await client.put('tutor/v1-e2e/stats/today', {'new_cap': 25});
    expect(jsonEncode(db.root), isNot(contains('new_cap')));
    expect(await client.get('tutor/v1-e2e/stats/today/new_cap'), 25);
    expect(await client.get('tutor/v1-e2e/stats/today/nope/x'), isNull);
    expect((await client.getTagged('$session/user')).value, {'archived': true});
    final put = await openEvent(
      client,
      session,
      RtdbPut('/', getAt(db.root, session)),
    );
    expect((put as RtdbPut).data, {
      'user': {'archived': true},
    });
    final patch = await openEvent(
      client,
      'tutor/v1-e2e/stats',
      RtdbPatch('/', {'today': getAt(db.root, 'tutor/v1-e2e/stats/today')}),
    );
    expect((patch as RtdbPatch).data, {
      'today': {'new_cap': 25},
    });
    expect(
      await openEvent(client, session, const RtdbKeepAlive()),
      isA<RtdbKeepAlive>(),
    );
    final cond = await client.putIfMatch('tutor/v1-e2e/stats/today', {
      'n': 1,
    }, 'x');
    expect(cond.value, {'n': 1});
    // Outside the e2e root nothing is sealed (the header lives there).
    await client.put('tutor/e2e', 'header');
    expect(getAt(db.root, 'tutor/e2e'), 'header');
  });

  test(
    'a stream event inside a unit drops the connection, then resyncs',
    () async {
      final sse = StreamController<List<int>>();
      final client = RtdbClient(
        layout: tutorLayout,
        databaseUrl: 'https://db',
        idToken: () async => 'tok',
        httpClient: MockClient.streaming(
          (req, _) async => http.StreamedResponse(sse.stream, 200),
        ),
        namespace: '',
      )..sealer = vectorSealer();
      final events = <RtdbEvent>[];
      final sub = RtdbStream(
        client,
        sleep: (_) => Completer<void>().future,
      ).listen('tutor/v1-e2e/stats/today').listen(events.add);
      sse.add(utf8.encode('event: put\ndata: {"path":"/x","data":1}\n\n'));
      await pumpEventQueue();
      expect(events.last, isA<RtdbDisconnected>());
      await sub.cancel();
    },
  );
}
