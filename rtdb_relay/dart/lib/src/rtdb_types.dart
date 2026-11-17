/// The REST client's value types: token source, errors, ETag pairs and the
/// `$key` range query.
library;

import 'dart:convert';

/// Supplies a currently valid Firebase ID token.
typedef IdTokenSource = Future<String> Function();

/// A failed RTDB request. [status] is null for network failures.
class RtdbError implements Exception {
  /// Creates the error.
  const new(this.message, {this.status});

  /// What failed, with the HTTP body when there was one.
  final String message;

  /// HTTP status, or null when the request never got an answer.
  final int? status;

  /// True when the rules or the token rejected this request (401/403).
  bool get isAuth => status == 401 || status == 403;

  /// True when retrying the same request can succeed (network, 5xx).
  bool get isTransient => status == null || status! >= 500;

  @override
  String toString() => 'RtdbError($status): $message';
}

/// A value read together with the ETag a conditional write must match.
class Tagged {
  /// Creates the pair.
  const new(this.value, this.etag);

  /// The decoded JSON value (null when the node is absent).
  final Object? value;

  /// The opaque ETag of [value].
  final String etag;
}

/// Result of a conditional PUT/DELETE.
class ConditionalResult {
  /// Creates the result.
  const new({required this.ok, required this.value, required this.etag});

  /// False on 412: another writer won the race.
  final bool ok;

  /// The written value (server values resolved), or the current one on 412.
  final Object? value;

  /// ETag of [value] after the call, when the server sent one.
  final String? etag;
}

/// Query parameters for a `$key`-ordered read starting at [startAt].
///
/// RTDB wants both values JSON-quoted. Only `orderBy="$key"` is usable:
/// the shared rules add no `.indexOn`.
Map<String, String> keyRangeQuery(String startAt) => {
  'orderBy': jsonEncode(r'$key'),
  'startAt': jsonEncode(startAt),
};
