/// Characters Realtime Database forbids in a key, plus `~` itself because it
/// is this module's escape character.
///
/// `/` is absent deliberately: it is the path separator, so it is handled by
/// splitting into segments before any segment is escaped.
const _escapedChars = {
  '~': '~7E',
  '.': '~2E',
  r'$': '~24',
  '#': '~23',
  '[': '~5B',
  ']': '~5D',
};

/// Escapes one path segment into a legal Realtime Database key.
///
/// RTDB rejects `. $ # [ ] /` in keys, and the REST API's trailing `.json`
/// is a *format suffix* rather than part of the path -- so a filename like
/// `log.json` cannot be stored verbatim. The mapping is a reversible `~XX`
/// hex escape (`log.json` -> `log~2Ejson`) rather than a lossy "strip the
/// extension", because callers see these names again: todo-app's
/// `listDirectory('todo-sync/notes')` returns *filenames*, not device
/// directories, and must keep getting `<uuid>.json` back.
///
/// `~` is used as the escape character because it is legal in RTDB keys and
/// unreserved in URLs, so the escaped form needs no percent-encoding -- which
/// would otherwise be decoded back into the illegal character by the server.
String encodeKey(String segment) {
  final buffer = StringBuffer();
  for (final rune in segment.split('')) {
    buffer.write(_escapedChars[rune] ?? rune);
  }
  return buffer.toString();
}

/// Reverses [encodeKey].
String decodeKey(String key) {
  final buffer = StringBuffer();
  var index = 0;
  while (index < key.length) {
    final escape = key.length - index >= 3
        ? key.substring(index, index + 3)
        : '';
    final decoded = _escapeToChar[escape];
    if (decoded == null) {
      buffer.write(key[index]);
      index += 1;
    } else {
      buffer.write(decoded);
      index += 3;
    }
  }
  return buffer.toString();
}

final Map<String, String> _escapeToChar = {
  for (final entry in _escapedChars.entries) entry.value: entry.key,
};

/// Escapes every segment of a `/`-separated logical path.
String encodePath(String path) =>
    path.split('/').where((s) => s.isNotEmpty).map(encodeKey).join('/');
