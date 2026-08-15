import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

/// First-stage response of the GitHub OAuth Device Flow: the code the user
/// types on github.com and the URL to type it into.
class DeviceCodeResponse {
  /// Creates a [DeviceCodeResponse] from its stored fields.
  const DeviceCodeResponse({
    required this.deviceCode,
    required this.userCode,
    required this.verificationUri,
    required this.interval,
    required this.expiresIn,
  });

  /// Builds a [DeviceCodeResponse] from GitHub's device-code JSON response.
  factory DeviceCodeResponse.fromJson(Map<String, dynamic> json) {
    return DeviceCodeResponse(
      deviceCode: json['device_code'] as String,
      userCode: json['user_code'] as String,
      verificationUri: json['verification_uri'] as String,
      interval: (json['interval'] as int?) ?? 5,
      expiresIn: (json['expires_in'] as int?) ?? 900,
    );
  }

  /// Opaque code the client polls with (not shown to the user).
  final String deviceCode;

  /// Short code the user enters on the verification page.
  final String userCode;

  /// Page the user opens to enter [userCode] (github.com/login/device).
  final String verificationUri;

  /// Minimum seconds to wait between polls.
  final int interval;

  /// Seconds until [deviceCode] expires.
  final int expiresIn;
}

/// Raised when the device-flow authorization fails or is declined.
class DeviceAuthException implements Exception {
  /// Creates a [DeviceAuthException] from GitHub's [code] and [message].
  DeviceAuthException(this.code, this.message);

  /// GitHub error code, e.g. `access_denied`, `expired_token`.
  final String code;

  /// Human-readable description of [code].
  final String message;

  @override
  String toString() => 'DeviceAuthException($code): $message';
}

/// Implements the GitHub OAuth **Device Flow** so the user can authorize the
/// app by visiting a URL and entering a short code — no token pasting.
///
/// Device flow needs only a public `client_id` (no client secret), which
/// makes it safe for a distributed app. The resulting access token is then
/// used exactly like a PAT by [GitHubClient].
///
/// References:
/// - POST https://github.com/login/device/code
/// - POST https://github.com/login/oauth/access_token
class GitHubDeviceAuth {
  /// Creates a [GitHubDeviceAuth] for the given OAuth App [clientId].
  GitHubDeviceAuth({
    required this.clientId,
    this.scope = 'repo',
    http.Client? httpClient,
    Future<void> Function(Duration)? delay,
  }) : _http = httpClient ?? http.Client(),
       // Indirection so tests can skip real waiting between polls.
       _delay = delay ?? Future<void>.delayed;

  /// The GitHub OAuth App's public client id.
  final String clientId;

  /// OAuth scope requested. `repo` is required for private-repo contents.
  final String scope;

  final http.Client _http;
  final Future<void> Function(Duration) _delay;

  static const _deviceCodeUrl = 'https://github.com/login/device/code';
  static const _tokenUrl = 'https://github.com/login/oauth/access_token';
  static const _grantType = 'urn:ietf:params:oauth:grant-type:device_code';

  /// Step 1: ask GitHub for a device + user code.
  Future<DeviceCodeResponse> requestDeviceCode() async {
    final res = await _http.post(
      Uri.parse(_deviceCodeUrl),
      headers: const {'Accept': 'application/json'},
      body: {'client_id': clientId, 'scope': scope},
    );
    if (res.statusCode != 200) {
      throw DeviceAuthException('http_${res.statusCode}', res.body);
    }
    return DeviceCodeResponse.fromJson(
      jsonDecode(res.body) as Map<String, dynamic>,
    );
  }

  /// Step 2: poll until the user authorizes, returning the access token.
  ///
  /// Honors GitHub's pacing protocol: `authorization_pending` keeps polling,
  /// `slow_down` increases the interval, and terminal errors throw a
  /// [DeviceAuthException].
  Future<String> pollForToken(DeviceCodeResponse device) async {
    var intervalSeconds = device.interval;
    final deadline = DateTime.now().add(Duration(seconds: device.expiresIn));

    while (DateTime.now().isBefore(deadline)) {
      await _delay(Duration(seconds: intervalSeconds));
      final res = await _http.post(
        Uri.parse(_tokenUrl),
        headers: const {'Accept': 'application/json'},
        body: {
          'client_id': clientId,
          'device_code': device.deviceCode,
          'grant_type': _grantType,
        },
      );
      final json = jsonDecode(res.body) as Map<String, dynamic>;

      final token = json['access_token'] as String?;
      if (token != null) return token;

      switch (json['error'] as String?) {
        case 'authorization_pending':
          continue; // User has not finished authorizing yet.
        case 'slow_down':
          // GitHub asks us to back off; obey its new interval.
          intervalSeconds = (json['interval'] as int?) ?? intervalSeconds + 5;
        case final String error:
          throw DeviceAuthException(
            error,
            (json['error_description'] as String?) ?? error,
          );
        case null:
          throw DeviceAuthException('unknown', 'Unexpected response: $json');
      }
    }
    throw DeviceAuthException('expired_token', 'Device code expired.');
  }

  /// Closes the underlying HTTP client. Call once when done polling.
  void close() => _http.close();
}
