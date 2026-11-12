import 'e2e_cipher.dart';
import 'e2e_envelope.dart';
import 'e2e_key.dart';
import 'remote_store.dart';
import 'sync.dart';

/// A [RemoteStore] that seals every blob under `pathPrefix` (nested
/// `<device>/<file>` or flat `<node>.json`) except the header, as a
/// per-record envelope (ids and HLCs clear, names and values opaque), and
/// keys every revision under `revsPath`, so the remote is a blind relay.
///
/// Wrap the outermost store (above a `MirrorStore`) so every backend gets
/// ciphertext. Other paths pass through unchanged.
class EncryptingStore implements RemoteStore, BulkMapReader {
  EncryptingStore(
    this._inner,
    this._key, {
    required String pathPrefix,
    String? revsPath,
    String? e2ePath,
    bool acceptPlaintext = true,
  }) : _cipher = _key.cipher(acceptPlaintext: acceptPlaintext),
       _prefix = pathPrefix,
       _revs = revsPath ?? defaultRevsPath(pathPrefix),
       _header = e2ePath ?? defaultE2ePath(pathPrefix);

  final RemoteStore _inner;
  final E2eKey _key;

  /// The key this store seals with.
  E2eKey get key => _key;
  final E2eCipher _cipher;
  final String _prefix;
  final String _revs;
  final String _header;

  bool _isRev(String path) => path.startsWith('$_revs/');

  bool _isLog(String path) =>
      !_isRev(path) && path != _header && path.startsWith('$_prefix/');

  @override
  Future<String?> getFileText(String path) async {
    final text = await _inner.getFileText(path);
    if (text == null || !_isLog(path)) return text;
    return openLogText(text, _cipher, path: path);
  }

  @override
  Future<void> putFileText(
    String path,
    String text, {
    required String message,
  }) async {
    final stored = _isLog(path)
        ? await sealLogText(text, _cipher, path: path)
        : _isRev(path)
        ? await _key.revision(text)
        : text;
    await _inner.putFileText(path, stored, message: message);
  }

  @override
  Future<Map<String, String>> getStringMap(String path) async {
    if (_inner case final BulkMapReader reader) {
      final map = await reader.getStringMap(path);
      if (!_isLog('$path/x')) return map;
      final out = <String, String>{};
      for (final MapEntry(:key, :value) in map.entries) {
        final full = '$path/$key';
        if (!_isLog(full)) {
          out[key] = value;
          continue;
        }
        try {
          out[key] = await openLogText(value, _cipher, path: full);
        } on E2eDecryptError {
          // Unreadable entries are dropped, as a corrupt value would be.
        }
      }
      return out;
    }
    return const {};
  }

  @override
  Future<List<String>> listDirectory(String path) => _inner.listDirectory(path);

  @override
  Future<void> deleteFile(String path, {String message = ''}) =>
      _inner.deleteFile(path, message: message);

  @override
  Future<bool> canAccessRemote() => _inner.canAccessRemote();

  @override
  void close() => _inner.close();
}
