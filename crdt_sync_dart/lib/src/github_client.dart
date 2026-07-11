import 'dart:convert';

import 'package:http/http.dart' as http;

const _apiBase = 'https://api.github.com';
const _httpNotFound = 404;

/// Raised for a GitHub API failure the caller must not silently ignore.
class GitHubSyncError implements Exception {
  GitHubSyncError(this.message);

  final String message;

  @override
  String toString() => 'GitHubSyncError: $message';
}

/// Raised when the configured repo itself is unreachable.
///
/// Distinguished from a path-404 (nothing pushed to that path yet, which is
/// benign -- it just means no other device has synced before) so the caller
/// can tell "the repo name is wrong or the token isn't scoped to it" apart
/// from "no other device has synced yet".
class RepoNotFoundError extends GitHubSyncError {
  RepoNotFoundError(super.message);
}

/// Minimal GitHub Contents API client used as dumb file storage.
///
/// GitHub is used purely as file storage via the REST Contents API, not a
/// git clone -- there is no working tree and no git-level merge; the only
/// merge is the domain-level one in `mergeLogs`. Mirrors
/// `crdt_sync._github.GitHubSyncClient` on the Python side: unlike `todo`'s
/// original `GitHubClient`, [listDirectory] returns every entry name
/// regardless of type (not just files), because `crdt_sync`'s
/// `<pathPrefix>/<deviceId>/<filename>` layout needs to discover device
/// *subdirectories*; and [putFileText] resolves its own current SHA rather
/// than requiring the caller to track it.
class GitHubClient {
  GitHubClient({
    required this.owner,
    required this.repo,
    required String token,
    http.Client? httpClient,
  }) // Dart forbids private named params, so this can't be an initializing
    // formal; assign it explicitly.
    // ignore: prefer_initializing_formals
    : _token = token,
       _http = httpClient ?? http.Client();

  final String owner;
  final String repo;
  final String _token;
  final http.Client _http;

  Map<String, String> get _headers => {
    'Authorization': 'Bearer $_token',
    'Accept': 'application/vnd.github+json',
  };

  Uri _contentsUri(String path) =>
      Uri.parse('$_apiBase/repos/$owner/$repo/contents/$path');

  Future<http.Response> _get(String path) async {
    try {
      return await _http.get(_contentsUri(path), headers: _headers);
    } on http.ClientException catch (exc) {
      throw GitHubSyncError('network error reading $path: $exc');
    }
  }

  Future<bool> _repoExists() async {
    try {
      final res = await _http.get(
        Uri.parse('$_apiBase/repos/$owner/$repo'),
        headers: _headers,
      );
      return res.statusCode >= 200 && res.statusCode < 300;
    } on http.ClientException {
      return false;
    }
  }

  Future<void> _raiseForMissingPath(String path) async {
    if (!await _repoExists()) {
      throw RepoNotFoundError(
        '$owner/$repo not found, private without access, or the token '
        'lacks contents permission (while reading $path)',
      );
    }
  }

  /// Returns the entry names directly under [path] (empty if unused).
  ///
  /// Includes both files and subdirectories -- see the class doc for why
  /// this differs from a plain "list files" helper.
  Future<List<String>> listDirectory(String path) async {
    final res = await _get(path);
    if (res.statusCode == _httpNotFound) {
      await _raiseForMissingPath(path);
      return [];
    }
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw GitHubSyncError('GET $path (list) failed: ${res.statusCode}');
    }
    final decoded = jsonDecode(res.body);
    if (decoded is! List) return [];
    return decoded
        .whereType<Map<String, dynamic>>()
        .map((e) => e['name'])
        .whereType<String>()
        .toList();
  }

  /// Returns the decoded text content at [path], or null if unused.
  Future<String?> getFileText(String path) async {
    final res = await _get(path);
    if (res.statusCode == _httpNotFound) {
      await _raiseForMissingPath(path);
      return null;
    }
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw GitHubSyncError('GET $path failed: ${res.statusCode}');
    }
    final decoded = jsonDecode(res.body) as Map<String, dynamic>;
    final content = (decoded['content'] as String? ?? '').replaceAll('\n', '');
    return utf8.decode(base64.decode(content));
  }

  Future<String?> _existingSha(String path) async {
    final res = await _get(path);
    if (res.statusCode == _httpNotFound) {
      await _raiseForMissingPath(path);
      return null;
    }
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw GitHubSyncError('GET $path (for sha) failed: ${res.statusCode}');
    }
    final decoded = jsonDecode(res.body) as Map<String, dynamic>;
    return decoded['sha'] as String?;
  }

  /// Creates or updates the file at [path] with [text].
  Future<void> putFileText(
    String path,
    String text, {
    required String message,
  }) async {
    final sha = await _existingSha(path);
    final body = <String, dynamic>{
      'message': message,
      'content': base64.encode(utf8.encode(text)),
      'sha': ?sha,
    };
    late final http.Response res;
    try {
      res = await _http.put(
        _contentsUri(path),
        headers: _headers,
        body: jsonEncode(body),
      );
    } on http.ClientException catch (exc) {
      throw GitHubSyncError('network error pushing $path: $exc');
    }
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw GitHubSyncError('PUT $path failed: ${res.statusCode}');
    }
  }

  /// Returns whether the configured token can read this repo.
  ///
  /// A lightweight connection test for a settings "Test connection" button: it
  /// hits the bare repo endpoint, so it succeeds even before any file has been
  /// pushed. Never throws -- a network failure or missing repo returns false.
  Future<bool> canAccessRepo() => _repoExists();

  /// Deletes the file at [path], resolving its current sha itself so callers
  /// don't have to track it. A no-op if [path] does not exist.
  Future<void> deleteFile(
    String path, {
    String message = 'crdt_sync: delete',
  }) async {
    final sha = await _existingSha(path);
    if (sha == null) return;
    late final http.Response res;
    try {
      res = await _http.delete(
        _contentsUri(path),
        headers: _headers,
        body: jsonEncode({'message': message, 'sha': sha}),
      );
    } on http.ClientException catch (exc) {
      throw GitHubSyncError('network error deleting $path: $exc');
    }
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw GitHubSyncError('DELETE $path failed: ${res.statusCode}');
    }
  }

  void close() => _http.close();
}
