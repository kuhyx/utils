/// Server-sent events from the RTDB streaming API, parsed and typed.
///
/// Pure: no I/O, so every line-splitting and event-mapping edge is unit
/// tested without a socket. The transport lives in `rtdb_stream.dart`.
library;

import 'dart:convert';

/// One raw SSE frame: an `event:` name and its joined `data:` lines.
class SseFrame {
  /// Creates the frame.
  const new(this.event, this.data);

  /// The `event:` field (`put`, `patch`, `keep-alive`, ...).
  final String event;

  /// The `data:` lines joined with `\n`.
  final String data;
}

/// Splits a text stream into [SseFrame]s.
///
/// Feed decoded chunks in arrival order; a chunk may end mid-line or
/// mid-frame. A blank line dispatches the frame being built.
class SseParser {
  String _buffer = '';
  String _event = '';
  final List<String> _data = [];

  /// Adds [chunk] and returns the frames it completed.
  List<SseFrame> add(String chunk) {
    _buffer += chunk;
    final frames = <SseFrame>[];
    while (true) {
      final newline = _buffer.indexOf('\n');
      if (newline < 0) break;
      var line = _buffer.substring(0, newline);
      _buffer = _buffer.substring(newline + 1);
      if (line.endsWith('\r')) line = line.substring(0, line.length - 1);
      if (line.isEmpty) {
        if (_event.isNotEmpty || _data.isNotEmpty) {
          frames.add(SseFrame(_event, _data.join('\n')));
        }
        _event = '';
        _data.clear();
      } else if (line.startsWith('event:')) {
        _event = line.substring(6).trim();
      } else if (line.startsWith('data:')) {
        _data.add(line.substring(5).trimLeft());
      }
      // Comments (":...") and unknown fields are ignored, as SSE requires.
    }
    return frames;
  }
}

/// A typed RTDB stream event.
sealed class RtdbEvent {
  const new();

  /// Maps an SSE frame; null for frames the client ignores.
  static RtdbEvent? fromFrame(SseFrame frame) {
    switch (frame.event) {
      case 'put':
      case 'patch':
        final body = jsonDecode(frame.data) as Map<String, dynamic>;
        final path = body['path'] as String;
        return frame.event == 'put'
            ? RtdbPut(path, body['data'])
            : RtdbPatch(path, body['data'] as Map<String, dynamic>);
      case 'keep-alive':
        return const RtdbKeepAlive();
      case 'cancel':
        return RtdbCancel(frame.data);
      case 'auth_revoked':
        return const RtdbAuthRevoked();
    }
    return null;
  }
}

/// Emitted by the transport before each (re)connect's snapshot `put`.
class RtdbConnected extends RtdbEvent {
  /// Creates the marker.
  const new();
}

/// Emitted by the transport when a connection drops or fails to open; it
/// reconnects on its own after a backoff.
class RtdbDisconnected extends RtdbEvent {
  /// Creates the marker.
  const new(this.error);

  /// Why (an [Exception], an HTTP status error, or null for a clean end).
  final Object? error;
}

/// `put`: [data] replaces the node at [path] (relative to the listened path;
/// `/` on connect is the full snapshot).
class RtdbPut extends RtdbEvent {
  /// Creates the event.
  const new(this.path, this.data);

  /// Path relative to the listened location.
  final String path;

  /// New value (null deletes).
  final Object? data;
}

/// `patch`: each child of [data] replaces that child under [path].
class RtdbPatch extends RtdbEvent {
  /// Creates the event.
  const new(this.path, this.data);

  /// Path relative to the listened location.
  final String path;

  /// Children to replace.
  final Map<String, dynamic> data;
}

/// The server's liveness ping (every ~30 s with no data).
class RtdbKeepAlive extends RtdbEvent {
  /// Creates the event.
  const new();
}

/// The rules no longer allow this listen; the stream ends.
class RtdbCancel extends RtdbEvent {
  /// Creates the event.
  const new(this.reason);

  /// Server-provided reason text.
  final String reason;
}

/// The token expired; the transport reconnects with a fresh one.
class RtdbAuthRevoked extends RtdbEvent {
  /// Creates the event.
  const new();
}
