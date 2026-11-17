/// The redaction applied before a report leaves the device (from kartka's
/// `report_redact.dart`).
library;

final _urlTail = RegExp(
  r'''(https?://[^\s?#"'<>]*)([?#])(?!<redacted>)[^\s"'<>]*''',
);
final _userInfo = RegExp(r'''(https?://)[^\s/?#"'<>@]*@''');
final _email = RegExp(r'[\w.+-]+@[\w-]+(\.[\w-]+)+');
final _bearer = RegExp(r'\b(Bearer|Basic)\s+[^\s,;]+', caseSensitive: false);
final _jwt = RegExp(r'eyJ[\w-]+\.[\w-]+\.[\w-]*');
final _named = RegExp(
  r'\b(cookie|set-cookie|authorization|password|passwd|token|secret|'
  r'api[_-]?key|session)\b(\s*[:=]\s*)[^\s,]+',
  caseSensitive: false,
);
final _home = RegExp(r'/(home|Users)/[^/\s]+/');

/// [text] with URL queries and user info, emails, bearer and basic
/// credentials, JWTs, `name=value` secrets and the user name in home paths
/// replaced. Over-redaction is the cheap mistake: a report that loses a word
/// is still fixable, one that leaks a token is not.
String redactForReport(String text) => text
    .replaceAllMapped(_urlTail, (m) => '${m[1]}${m[2]}<redacted>')
    .replaceAllMapped(_userInfo, (m) => '${m[1]}<redacted>@')
    .replaceAll(_jwt, '<jwt>')
    .replaceAllMapped(_bearer, (m) => '${m[1]} <redacted>')
    .replaceAllMapped(_named, (m) => '${m[1]}${m[2]}<redacted>')
    .replaceAll(_email, '<email>')
    .replaceAll(_home, '~/');
