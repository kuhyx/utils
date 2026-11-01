import 'dart:convert';

/// Why a file is not an acceptable export envelope.
///
/// Always a [FormatException], so callers that only care about "bad file"
/// can keep catching that.
sealed class EnvelopeException implements FormatException {
  const EnvelopeException(this.message);

  @override
  final String message;

  @override
  dynamic get source => null;

  @override
  int? get offset => null;

  @override
  String toString() => 'EnvelopeException: $message';
}

/// The text is not JSON at all.
final class EnvelopeInvalidJson extends EnvelopeException {
  /// Creates the error.
  const EnvelopeInvalidJson() : super('not valid JSON');
}

/// The JSON is valid but its top level is not an object.
final class EnvelopeNotObject extends EnvelopeException {
  /// Creates the error.
  const EnvelopeNotObject() : super('export is not a JSON object');
}

/// The `format` marker is missing or names another kind of file.
final class EnvelopeFormatMismatch extends EnvelopeException {
  /// Creates the error for a file marked [actual] when [expected] was needed.
  EnvelopeFormatMismatch({required this.expected, required this.actual})
    : super('not a $expected file (found "$actual")');

  /// The format the caller accepts.
  final String expected;

  /// The format the file declared, `null` when it declared none.
  final Object? actual;
}

/// The `version` is missing or differs from the one the caller reads.
final class EnvelopeVersionMismatch extends EnvelopeException {
  /// Creates the error for a file at version [actual] when [expected] was
  /// needed.
  EnvelopeVersionMismatch({required this.expected, required this.actual})
    : super('unsupported version $actual (expected $expected)');

  /// The version the caller reads.
  final int expected;

  /// The version the file declared, `null` when it declared none.
  final Object? actual;
}

/// Builds `{format, version, exported_at, ...body}`, in that key order.
///
/// [now] is converted to UTC. Throws [ArgumentError] when [body] reuses an
/// envelope key, which would silently corrupt the marker.
Map<String, Object?> buildEnvelope({
  required String format,
  required int version,
  required DateTime now,
  Map<String, Object?> body = const {},
}) {
  const reserved = {'format', 'version', 'exported_at'};
  final clash = body.keys.where(reserved.contains).toList();
  if (clash.isNotEmpty) {
    throw ArgumentError.value(body, 'body', 'reuses envelope keys: $clash');
  }
  return <String, Object?>{
    'format': format,
    'version': version,
    'exported_at': now.toUtc().toIso8601String(),
    ...body,
  };
}

/// Returns [decoded] when it is an object marked [format] at [version].
///
/// Throws an [EnvelopeException] subtype otherwise.
Map<String, Object?> validateEnvelope(
  Object? decoded, {
  required String format,
  required int version,
}) {
  if (decoded is! Map<String, Object?>) throw const EnvelopeNotObject();
  final actualFormat = decoded['format'];
  if (actualFormat != format) {
    throw EnvelopeFormatMismatch(expected: format, actual: actualFormat);
  }
  final actualVersion = decoded['version'];
  if (actualVersion != version) {
    throw EnvelopeVersionMismatch(expected: version, actual: actualVersion);
  }
  return decoded;
}

/// Decodes [text] and runs [validateEnvelope] on it.
Map<String, Object?> parseEnvelope(
  String text, {
  required String format,
  required int version,
}) {
  final Object? decoded;
  try {
    decoded = jsonDecode(text);
  } on FormatException {
    throw const EnvelopeInvalidJson();
  }
  return validateEnvelope(decoded, format: format, version: version);
}
