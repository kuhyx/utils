/// One error or slow-wait report, in the shape every reporter (Dart, Python,
/// GDScript) writes and utils `app_errors` ingests (its README, "Entry").
library;

/// The kind of a user-visible wait that lasted over a second.
const perfSlowKind = 'perf.slow';

/// One report, before the uploader adds the app's repo, mark and build.
class ErrorEntry {
  /// A report of [kind] at [at].
  const ErrorEntry({
    required this.at,
    required this.kind,
    required this.error,
    this.stack = const [],
    this.route,
    this.operation,
    this.durationMs,
    this.waitId,
    this.still,
  });

  /// Decodes [toJson]'s shape; throws on a wrong one ([tryFromJson] does not).
  factory ErrorEntry.fromJson(Map<String, Object?> json) => ErrorEntry(
    at: DateTime.parse(json['at']! as String),
    kind: json['kind']! as String,
    error: json['error']! as String,
    stack: [for (final f in json['stack'] as List<Object?>? ?? []) '$f'],
    route: json['route'] as String?,
    operation: json['operation'] as String?,
    durationMs: json['durationMs'] as int?,
    waitId: json['waitId'] as String?,
    still: json['still'] as bool?,
  );

  /// [ErrorEntry.fromJson], or null when [json] is not an entry.
  static ErrorEntry? tryFromJson(Object? json) {
    try {
      return ErrorEntry.fromJson(json! as Map<String, Object?>);
    } on Object {
      return null;
    }
  }

  /// When it happened (UTC).
  final DateTime at;

  /// `uncaught.flutter`, `uncaught.async`, `perf.slow`, ...
  final String kind;

  /// The error's text (a slow wait: `<operation> waited <ms> ms`).
  final String error;

  /// The innermost frames, then the app's own.
  final List<String> stack;

  /// The route on top when it happened (a pattern, never an id).
  final String? route;

  /// What a slow wait waited for (`list.load`).
  final String? operation;

  /// How long a slow wait took.
  final int? durationMs;

  /// Names one slow wait across its still-going and final reports.
  final String? waitId;

  /// True for the report of a wait that has not ended yet.
  final bool? still;

  /// The JSON shape (absent fields are left out).
  Map<String, Object?> toJson() => {
    'at': at.toUtc().toIso8601String(),
    'kind': kind,
    'error': error,
    'stack': stack,
    'route': ?route,
    'operation': ?operation,
    'durationMs': ?durationMs,
    'waitId': ?waitId,
    'still': ?still,
  };
}
