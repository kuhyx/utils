import 'e2e_cipher.dart';
import 'e2e_envelope.dart';
import 'firebase_keys.dart';

/// Plaintext leaves in a decoded RTDB dump; empty once an app is migrated.
/// Decodes because RTDB serves blobs as escaped strings that defeat grep.
List<String> plaintextBlobPaths(Object? tree) {
  final found = <String>[];
  void walk(Object? node, String path) {
    if (node is String) {
      if (E2eCipher.isPlaintext(node) && !isE2eEnvelope(node)) found.add(path);
    } else if (node is Map) {
      for (final MapEntry(:key, :value) in node.entries) {
        if (key == 'e2e' && value is String) continue;
        final segment = decodeKey(key as String);
        walk(value, path.isEmpty ? segment : '$path/$segment');
      }
    }
  }

  walk(tree, '');
  return found;
}
