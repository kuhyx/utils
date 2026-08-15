import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:github_device_auth/github_device_auth.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _device = DeviceCodeResponse(
  deviceCode: 'dc',
  userCode: 'ABCD-1234',
  verificationUri: 'https://github.com/login/device',
  interval: 1,
  expiresIn: 60,
);

/// Completes immediately -- for tests whose mock resolves on the first poll.
Future<void> _noDelay(Duration _) async {}

/// Never completes, so the poll loop suspends on its first delay.
///
/// The pending-state tests need the dialog to sit in "waiting" without
/// actually looping: with an instantly-completing delay and a mock that
/// always answers `authorization_pending`, `pollForToken` spins as fast as
/// the event loop allows and starves the test binding.
Future<void> _neverDelay(Duration _) => Completer<void>().future;

GitHubDeviceAuth _auth(
  MockClient client, {
  Future<void> Function(Duration) delay = _noDelay,
}) => GitHubDeviceAuth(clientId: 'cid', httpClient: client, delay: delay);

/// An auth client that never gets past its first poll delay.
GitHubDeviceAuth _pendingAuth() => _auth(
  MockClient(
    (_) async => http.Response(jsonEncode({'error': 'authorization_pending'}), 200),
  ),
  delay: _neverDelay,
);

/// Opens the dialog and returns a getter for whatever it eventually pops.
///
/// The result is read through a closure rather than returned directly
/// because the dialog may still be polling when this returns -- a test that
/// cares about the popped value pumps first, then reads.
Future<Object? Function()> _showDialog(
  WidgetTester tester,
  GitHubDeviceAuth auth,
) async {
  Object? popped;
  await tester.pumpWidget(
    MaterialApp(
      home: Builder(
        builder: (context) => ElevatedButton(
          onPressed: () async {
            popped = await showDialog<String>(
              context: context,
              builder: (_) => DeviceCodeDialog(device: _device, auth: auth),
            );
          },
          child: const Text('open'),
        ),
      ),
    ),
  );
  await tester.tap(find.text('open'));
  await tester.pump();
  return () => popped;
}

void main() {
  testWidgets('shows the user code and a waiting state', (tester) async {
    await _showDialog(tester, _pendingAuth());

    expect(find.text('Authorize on GitHub'), findsOneWidget);
    expect(find.text('ABCD-1234'), findsOneWidget);
    expect(find.text('Waiting for authorization…'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });

  testWidgets('pops the token once authorized', (tester) async {
    final auth = _auth(
      MockClient(
        (_) async => http.Response(jsonEncode({'access_token': 'tok'}), 200),
      ),
    );

    final popped = await _showDialog(tester, auth);
    await tester.pumpAndSettle();

    expect(find.byType(AlertDialog), findsNothing);
    expect(popped(), 'tok');
  });

  testWidgets('shows the error instead of spinning forever', (tester) async {
    final auth = _auth(
      MockClient(
        (_) async => http.Response(
          jsonEncode({
            'error': 'access_denied',
            'error_description': 'user declined',
          }),
          200,
        ),
      ),
    );

    await _showDialog(tester, auth);
    await tester.pump();

    expect(find.byType(CircularProgressIndicator), findsNothing);
    expect(find.textContaining('access_denied'), findsOneWidget);
  });

  testWidgets('surfaces an Error, not just an Exception', (tester) async {
    // The regression this dialog's `on Object catch` exists for: an
    // `ArgumentError` is an Error, not an Exception, so `on Exception` would
    // let it escape and leave the dialog spinning with nothing shown.
    final auth = _auth(
      MockClient((_) async => throw ArgumentError('No host specified in URI')),
    );

    await _showDialog(tester, auth);
    await tester.pump();

    expect(find.byType(CircularProgressIndicator), findsNothing);
    expect(find.textContaining('No host specified'), findsOneWidget);
  });

  testWidgets('cancel pops without a token', (tester) async {
    final popped = await _showDialog(tester, _pendingAuth());
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();

    expect(find.byType(AlertDialog), findsNothing);
    expect(popped(), isNull);
  });

  testWidgets('the action button copies the code to the clipboard', (
    tester,
  ) async {
    final auth = _pendingAuth();

    String? copied;
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (call) async {
        if (call.method == 'Clipboard.setData') {
          copied =
              ((call.arguments as Map<Object?, Object?>)['text'] as String?);
        }
        return null;
      },
    );
    // url_launcher would otherwise hit a missing plugin on the test binding.
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/url_launcher'),
      (_) async => true,
    );

    await _showDialog(tester, auth);
    await tester.tap(find.text('Open GitHub & copy code'));
    await tester.pump();

    expect(copied, 'ABCD-1234');
  });
}
