/// The RTDB streaming transport: one long-lived `text/event-stream` GET per
/// listened path, reconnecting until the listener cancels.
///
/// Every (re)connect resends the full snapshot of the path, so callers listen
/// narrowly (tutor DOCS-contract §9). `auth_revoked` reconnects at once with a
/// fresh token; network failures and clean ends back off 1 s .. 30 s;
/// `cancel` (rules changed) ends the stream for good.
///
/// RTDB speaks HTTP/1.1, so a browser holds at most 6 connections to it and
/// every listen is one. The app keeps at most 4 open, leaving 2 for writes
/// and reads (tutor DOCS-contract §9). A cancelled
/// listen therefore aborts its request, even one still connecting: a leaked
/// stream starved the next session's listens and the chat stayed empty after
/// Next card (2026-10-12).
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:http/http.dart' as http;
import 'package:rtdb_relay/src/rtdb_client.dart';
import 'package:rtdb_relay/src/rtdb_event.dart';

/// Waits [d]; injectable so tests run the reconnect loop without real time.
typedef Sleep = Future<void> Function(Duration d);

/// Backoff before reconnect attempt [n] (0-based): 1, 2, 4 .. 30 s.
Duration reconnectDelay(int n) => Duration(seconds: n >= 5 ? 30 : 1 << n);

enum _End { reconnectNow, backoff, stop }

/// Opens SSE listens through an [RtdbClient].
class RtdbStream {
  /// Creates the transport.
  new(this.client, {Sleep? sleep}) : _sleep = sleep ?? Future<void>.delayed;

  /// Supplies URLs (with fresh tokens) and the HTTP client.
  final RtdbClient client;
  final Sleep _sleep;

  /// Streams events for [path] until the subscription is cancelled.
  Stream<RtdbEvent> listen(
    String path, {
    Map<String, String> query = const {},
  }) {
    late final StreamController<RtdbEvent> out;
    StreamSubscription<String>? sub;
    final abort = Completer<void>();
    var stopped = false;
    void emit(RtdbEvent event) {
      if (!stopped && !out.isClosed) out.add(event);
    }

    // Sealed units open asynchronously; a chain keeps the events in order.
    final sealed = client.e2eRel(path) != null;
    var chain = Future<void>.value();

    Future<_End> consume(http.StreamedResponse res) {
      final done = Completer<_End>();
      final parser = SseParser();
      void finish(_End end) {
        if (!done.isCompleted) done.complete(end);
      }

      sub = res.stream
          .transform(utf8.decoder)
          .listen(
            (chunk) {
              for (final frame in parser.add(chunk)) {
                if (done.isCompleted) return;
                final RtdbEvent? event;
                try {
                  event = RtdbEvent.fromFrame(frame);
                } on Object catch (error) {
                  // A malformed frame: drop the connection and resync from
                  // the next snapshot rather than apply half an update.
                  emit(RtdbDisconnected(error));
                  finish(_End.backoff);
                  return;
                }
                if (event == null) continue;
                if (!sealed) {
                  emit(event);
                } else {
                  final sealedEvent = event;
                  chain = chain.then((_) async {
                    try {
                      emit(await openEvent(client, path, sealedEvent));
                    } on Object catch (error) {
                      // Locked, or an event inside a unit: resync later.
                      emit(RtdbDisconnected(error));
                      finish(_End.backoff);
                    }
                  });
                }
                if (event is RtdbAuthRevoked) finish(_End.reconnectNow);
                if (event is RtdbCancel) finish(_End.stop);
              }
            },
            onError: (Object e) {
              emit(RtdbDisconnected(e));
              finish(_End.backoff);
            },
            onDone: () {
              chain = chain.then((_) {
                emit(const RtdbDisconnected(null));
                finish(_End.backoff);
              });
            },
          );
      return done.future;
    }

    Future<void> run() async {
      var attempt = 0;
      while (!stopped) {
        var end = _End.backoff;
        try {
          final res = await _open(
            await client.uri(path, query: query),
            abort.future,
          );
          if (stopped) {
            // Cancelled while connecting: let go of the response too.
            await res.stream.listen(null).cancel();
            break;
          }
          attempt = 0;
          emit(const RtdbConnected());
          end = await consume(res);
          await sub?.cancel();
        } on Object catch (error) {
          // `on Object`: a token failure is a FirebaseAuthError, a bad frame
          // a FormatException, a dropped socket a ClientException; all of
          // them mean "try again later", never "crash the listener".
          emit(RtdbDisconnected(error));
        }
        if (end == _End.stop || stopped) break;
        if (end == _End.backoff) await _sleep(reconnectDelay(attempt++));
      }
      if (!out.isClosed) await out.close();
    }

    out = StreamController<RtdbEvent>(
      onListen: () => unawaited(run()),
      onCancel: () async {
        stopped = true;
        if (!abort.isCompleted) abort.complete();
        await sub?.cancel();
      },
    );
    return out.stream;
  }

  /// GET with `Accept: text/event-stream`, following redirects by hand so
  /// the Accept header survives a 307 to another RTDB host.
  Future<http.StreamedResponse> _open(Uri uri, Future<void> abort) async {
    var target = uri;
    for (var hop = 0; hop < 5; hop++) {
      final request = http.AbortableRequest('GET', target, abortTrigger: abort)
        // A browser's fetch cannot hand a redirect back (http's
        // BrowserClient raises instead) and follows it keeping Accept, so
        // only the VM follows by hand.
        ..followRedirects = kIsWeb
        ..headers['Accept'] = 'text/event-stream';
      final res = await client.httpClient.send(request);
      final location = res.headers['location'];
      if (res.statusCode >= 300 && res.statusCode < 400 && location != null) {
        await res.stream.drain<void>();
        target = target.resolve(location);
        continue;
      }
      if (res.statusCode != 200) {
        final body = await res.stream.bytesToString();
        throw RtdbError(
          'stream ${uri.path}: HTTP ${res.statusCode} ${body.trim()}',
          status: res.statusCode,
        );
      }
      return res;
    }
    throw RtdbError('stream ${uri.path}: too many redirects');
  }
}

/// [event] (from a listen on [listened]) with its sealed units opened.
Future<RtdbEvent> openEvent(
  RtdbClient client,
  String listened,
  RtdbEvent event,
) async {
  String at(String rel) => [
    listened,
    rel,
  ].expand((p) => p.split('/')).where((s) => s.isNotEmpty).join('/');
  switch (event) {
    case RtdbPut():
      return RtdbPut(
        event.path,
        await client.opened(at(event.path), event.data),
      );
    case RtdbPatch():
      return RtdbPatch(event.path, {
        for (final e in event.data.entries)
          e.key: await client.opened(at('${event.path}/${e.key}'), e.value),
      });
    default:
      return event;
  }
}
