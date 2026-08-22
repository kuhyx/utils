/// An in-memory stand-in for the `flutter_secure_storage` platform channel.
///
/// Shipped from the package rather than copied into each app's `test/`: the
/// glue this package owns is exactly the glue that cannot be tested without
/// it, and a consumer adopting the package should not have to reinvent the
/// fake to test its own sync wiring.
library;

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// Installs the fake for the duration of the current test.
///
/// Auto-removes on tear down. Pass [initial] to pre-seed stored values, and
/// [throwing] to simulate a host with no secret service -- every call then
/// raises a [PlatformException], which is what a Linux box with no libsecret
/// actually does.
void installFakeSecureStorage({
  Map<String, String>? initial,
  bool throwing = false,
}) {
  const channel = MethodChannel('plugins.it_nomads.com/flutter_secure_storage');
  final store = <String, String>{...?initial};
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  void setHandler(Future<Object?>? Function(MethodCall)? handler) =>
      messenger.setMockMethodCallHandler(channel, handler);

  setHandler((call) async {
    if (throwing) {
      throw PlatformException(code: 'unavailable');
    }
    final args = (call.arguments as Map?) ?? const <Object?, Object?>{};
    final key = args['key'] as String?;
    switch (call.method) {
      case 'read':
        return store[key];
      case 'write':
        store[key!] = args['value']! as String;
        return null;
      case 'delete':
        store.remove(key);
        return null;
      case 'containsKey':
        return store.containsKey(key);
      case 'readAll':
        return Map<String, String>.from(store);
      case 'deleteAll':
        store.clear();
        return null;
      default:
        return null;
    }
  });

  addTearDown(() => setHandler(null));
}
