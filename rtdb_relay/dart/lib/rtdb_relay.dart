/// The Flutter client half of the sealed RTDB request relay: REST + SSE
/// over Firebase RTDB, end-to-end sealing per an app's [RelayLayout], the
/// shared `requests` listen, the `rev` watcher, the passphrase gate and the
/// Google -> Firebase session. The PC half is the Python `rtdb_relay`.
library;

export 'src/auth.dart';
export 'src/e2e_gate.dart';
export 'src/json_tree.dart';
export 'src/layout.dart';
export 'src/request_hub.dart';
export 'src/rev_watcher.dart';
export 'src/rtdb_client.dart';
export 'src/rtdb_event.dart';
export 'src/rtdb_stream.dart';
export 'src/sealer.dart';
export 'src/wrapper_credentials.dart';
