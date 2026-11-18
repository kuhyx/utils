/// Unlocks an app's e2e key: Argon2id of the shared crdt-sync passphrase,
/// read from and cached in the OS keystore by crdt_sync_flutter
/// (tutor DOCS-contract §12). Until it opens, [RtdbClient] sends nothing.
library;

import 'package:crdt_sync/crdt_sync.dart'
    show
        Argon2Params,
        E2eLockReason,
        E2eLocked,
        E2eReady,
        E2eState,
        RemoteStore,
        RemoteSyncError;
import 'package:crdt_sync_flutter/crdt_sync_flutter.dart'
    show kSecureStorage, openEncryptedStoreFromKeystore, saveE2ePassphrase;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:rtdb_relay/src/rtdb_client.dart';
import 'package:rtdb_relay/src/sealer.dart';

/// Opens [client]'s sealer from the keystore; [locked] until it did.
class E2eGate {
  /// Creates the gate. [params] is lowered only by tests.
  new({
    required this.client,
    this.storage = kSecureStorage,
    this.params = Argon2Params.recommended,
    this.recover,
  });

  /// The client whose sealer this sets.
  final RtdbClient client;

  /// The keystore holding the passphrase and the cached key.
  final FlutterSecureStorage storage;

  /// Argon2id cost for a header this device creates.
  final Argon2Params params;

  /// Where a missing or wrong passphrase can be fetched from (the desktop:
  /// its PC wrapper, `fetchWrapperPassphrase`). Asked at most once per gate,
  /// so a wrong answer cannot loop; the manual entry stays the fallback.
  final Future<String?> Function()? recover;

  bool _recovered = false;

  /// Why the last [unlock] stayed locked; null once open.
  E2eState? last;

  /// True while the client needs a key and has none (nothing is sent).
  /// A client built without `sealRequired` (tests, fixtures) never locks.
  bool get locked => client.sealRequired && client.sealer == null;

  /// Opens the key (header made on first use); true when unlocked.
  ///
  /// The crdt_sync log copy inside `openEncryptedStore` finds nothing to
  /// copy here ([E2eHeaderStore] lists no directory): a relay tree is
  /// not a crdt log; the PC worker copies the old root itself.
  Future<bool> unlock() async {
    if (!locked) return true;
    var state = await _open();
    final fetch = recover;
    if (fetch != null && !_recovered && _passphraseIsTheProblem(state)) {
      _recovered = true;
      final secret = await fetch();
      if (secret != null) {
        await saveE2ePassphrase(secret, storage: storage);
        state = await _open();
      }
    }
    last = state;
    if (state is E2eReady) {
      client.sealer = RelaySealer(
        state.store.key.cipher(),
        layout: client.layout,
      );
      return true;
    }
    return false;
  }

  Future<E2eState> _open() => openEncryptedStoreFromKeystore(
    store: E2eHeaderStore(client),
    oldPrefix: client.layout.base,
    storage: storage,
    params: params,
  );

  static bool _passphraseIsTheProblem(E2eState state) => switch (state) {
    E2eLocked(
      reason: E2eLockReason.needsPassphrase || E2eLockReason.wrongKey,
    ) =>
      true,
    _ => false,
  };

  /// The lock reason of the last attempt, for the spoken label.
  String get reason => switch (last) {
    E2eLocked(:final reason) => reason.name,
    _ => '',
  };
}

/// Just enough of crdt_sync's [RemoteStore] for the e2e header: one JSON
/// string leaf (`<base>/e2e`, e.g. `tutor/e2e`), as the PC worker writes it.
class E2eHeaderStore implements RemoteStore {
  /// Creates the store over [_client] (no sealing outside the e2e root).
  new(this._client);

  final RtdbClient _client;

  @override
  Future<String?> getFileText(String path) async {
    final value = await _client.get(path);
    if (value == null || value is String) return value as String?;
    // Not a header we wrote: unlock reports badHeader, never overwrites it.
    return '$value';
  }

  @override
  Future<void> putFileText(
    String path,
    String text, {
    required String message,
  }) async {
    await _client.put(path, text);
  }

  @override
  Future<List<String>> listDirectory(String path) async => const [];

  @override
  Future<void> deleteFile(String path, {String message = ''}) =>
      throw RemoteSyncError('the relay never deletes the e2e header');

  @override
  Future<bool> canAccessRemote() async => true;

  @override
  void close() {}
}
