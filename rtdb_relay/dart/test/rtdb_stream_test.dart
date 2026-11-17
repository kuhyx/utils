import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:rtdb_relay/src/rtdb_client.dart';
import 'package:rtdb_relay/src/rtdb_event.dart';
import 'package:rtdb_relay/src/rtdb_stream.dart';

import 'support/tutor_layout.dart';

/// Scripted server: each connection takes the next response factory.
class _Server {
  final List<http.StreamedResponse Function(http.BaseRequest)> script = [];
  final List<http.BaseRequest> requests = [];
  final List<Duration> slept = [];

  RtdbStream stream() {
    final client = MockClient.streaming((req, _) async {
      requests.add(req);
      if (script.isEmpty) return _never();
      return script.removeAt(0)(req);
    });
    return RtdbStream(
      RtdbClient(
        layout: tutorLayout,
        databaseUrl: 'https://db',
        idToken: () async => 'tok',
        httpClient: client,
      ),
      sleep: (d) async => slept.add(d),
    );
  }
}

http.StreamedResponse _sse(List<String> chunks, {bool close = true}) {
  final c = StreamController<List<int>>();
  for (final chunk in chunks) {
    c.add(utf8.encode(chunk));
  }
  if (close) unawaited(c.close());
  return http.StreamedResponse(c.stream, 200);
}

http.StreamedResponse _never() =>
    http.StreamedResponse(StreamController<List<int>>().stream, 200);

String _frame(String event, String data) => 'event: $event\ndata: $data\n\n';

void main() {
  test('reconnectDelay doubles to a 30 s cap', () {
    expect(
      [for (var i = 0; i < 7; i++) reconnectDelay(i).inSeconds],
      [
        1, 2, 4, 8, 16, 30, 30, //
      ],
    );
  });

  test(
    'snapshot, keep-alive, auth_revoked reconnects now, cancel ends',
    () async {
      final s = _Server()
        ..script.add(
          (_) => _sse([
            _frame('put', '{"path":"/","data":{"a":1}}'),
            _frame('keep-alive', 'null'),
            _frame('auth_revoked', 'credential is no longer valid'),
            _frame('put', '{"path":"/late","data":1}'),
          ], close: false),
        )
        ..script.add((_) => _sse([_frame('cancel', 'permission denied')]));
      final events = await s.stream().listen('tutor/v1-e2e/presence').toList();
      expect(events.map((e) => e.runtimeType).toList(), [
        RtdbConnected,
        RtdbPut,
        RtdbKeepAlive,
        RtdbAuthRevoked,
        RtdbConnected,
        RtdbCancel,
      ]);
      expect(s.slept, isEmpty);
      expect(s.requests.first.headers['Accept'], 'text/event-stream');
    },
  );

  test('follows a 307 keeping Accept; HTTP error backs off', () async {
    final s = _Server()
      ..script.add(
        (_) => http.StreamedResponse(
          const Stream.empty(),
          307,
          headers: {'location': 'https://other/x.json?auth=t'},
        ),
      )
      ..script.add(
        (_) => http.StreamedResponse(Stream.value(utf8.encode('no')), 401),
      )
      ..script.add((_) => _sse([_frame('cancel', 'bye')]));
    final events = await s.stream().listen('x').toList();
    expect(s.requests[1].url.host, 'other');
    expect(s.requests[1].headers['Accept'], 'text/event-stream');
    final err = (events.first as RtdbDisconnected).error! as RtdbError;
    expect(err.status, 401);
    expect(s.slept, [const Duration(seconds: 1)]);
    expect(events.last, isA<RtdbCancel>());
  });

  test('too many redirects is a disconnect', () async {
    final s = _Server();
    for (var i = 0; i < 5; i++) {
      s.script.add(
        (_) => http.StreamedResponse(
          const Stream.empty(),
          307,
          headers: {'location': '/again'},
        ),
      );
    }
    s.script.add((_) => _sse([_frame('cancel', 'bye')]));
    final events = await s.stream().listen('x').toList();
    expect((events.first as RtdbDisconnected).error, isA<RtdbError>());
  });

  test('clean end, socket error and bad frame all back off', () async {
    final broken = StreamController<List<int>>();
    final s = _Server()
      ..script.add((_) => _sse([]))
      ..script.add((_) {
        broken.addError(http.ClientException('reset'));
        return http.StreamedResponse(broken.stream, 200);
      })
      ..script.add((_) => _sse([_frame('put', 'not json')], close: false))
      ..script.add((_) => _sse([_frame('cancel', 'bye')]));
    final events = await s.stream().listen('x').toList();
    final drops = events.whereType<RtdbDisconnected>().toList();
    expect(drops[0].error, isNull);
    expect(drops[1].error, isA<http.ClientException>());
    expect(drops[2].error, isA<FormatException>());
    expect(s.slept, hasLength(3));
    await broken.close();
  });

  test('cancelling the subscription stops reconnecting', () async {
    final s = _Server()
      ..script.add(
        (_) => _sse([_frame('put', '{"path":"/","data":1}')], close: false),
      );
    final got = Completer<void>();
    final sub = s.stream().listen('x').listen((e) {
      if (e is RtdbPut) got.complete();
    });
    await got.future;
    await sub.cancel();
    await Future<void>.delayed(Duration.zero);
    expect(s.requests, hasLength(1));
  });

  test('a listen cancelled while connecting aborts and lets go', () async {
    // RTDB is HTTP/1.1: a browser has 6 connections to it. A leaked listen
    // starved the next session's meta/msgs (empty chat after Next card).
    final server = _Server();
    final gate = Completer<void>();
    var released = false;
    final body = StreamController<List<int>>(onCancel: () => released = true);
    server.script.add((_) => http.StreamedResponse(body.stream, 200));
    final client = MockClient.streaming((req, _) async {
      server.requests.add(req);
      await gate.future;
      return server.script.removeAt(0)(req);
    });
    final stream = RtdbStream(
      RtdbClient(
        layout: tutorLayout,
        databaseUrl: 'https://db',
        idToken: () async => 'tok',
        httpClient: client,
      ),
      sleep: (d) async {},
    );
    final sub = stream.listen('tutor/v1-e2e/live').listen((_) {});
    await Future<void>.delayed(Duration.zero);
    final req = server.requests.single as http.Abortable;
    var aborted = false;
    unawaited(req.abortTrigger!.then((_) => aborted = true));
    await sub.cancel();
    await Future<void>.delayed(Duration.zero);
    expect(aborted, isTrue);
    gate.complete();
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    expect(released, isTrue);
  });
}
