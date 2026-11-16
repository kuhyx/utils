/// The e2e header's Argon2id cost and the errors unlocking it can raise.
library;

/// Argon2id cost, stored in the header so it can be raised later.
class Argon2Params {
  const Argon2Params({
    required this.memoryKiB,
    required this.iterations,
    required this.parallelism,
  });

  /// OWASP's floor (19 MiB, t=2); higher stalls the Flutter-web desktop build.
  static const recommended = Argon2Params(
    memoryKiB: 19456,
    iterations: 2,
    parallelism: 1,
  );

  final int memoryKiB;
  final int iterations;
  final int parallelism;
}

class E2eHeaderError extends FormatException {
  E2eHeaderError(super.message);

  @override
  String toString() => 'E2eHeaderError: $message';
}

class E2eWrongPassphraseError implements Exception {
  @override
  String toString() => 'E2eWrongPassphraseError: wrong sync passphrase';
}
