/// Which app reports, and which build it is.
library;

/// The app's identity in its reports.
class AppErrorsConfig {
  /// The app [app] (as the board shows it), fixed in [repo] (`owner/name`).
  const AppErrorsConfig({
    required this.app,
    required this.repo,
    this.package,
    this.build = 0,
    this.version,
  });

  /// The app name: the RTDB root key and the board's `app`
  /// (`^[a-z0-9][a-z0-9_-]*$`).
  final String app;

  /// The repo that holds the fix (`kuhyx/todo`).
  final String repo;

  /// The Dart package name, when it is not [app] with `-` as `_`.
  final String? package;

  /// The build number (Android versionCode); 0 when unknown.
  final int build;

  /// The version name (`1.2.3`).
  final String? version;

  /// This config with [build] replaced.
  AppErrorsConfig withBuild(int build) => AppErrorsConfig(
    app: app,
    repo: repo,
    package: package,
    build: build,
    version: version,
  );

  /// What marks the app's own stack frames (`package:todo/`).
  String get mark => 'package:${package ?? app.replaceAll('-', '_')}/';
}
