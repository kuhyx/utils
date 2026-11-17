// The tutor app's layout (tutor DOCS-contract §12): the first consumer and
// the one its e2e vectors pin, so the tests run against the real tree.
import 'package:rtdb_relay/src/layout.dart';

/// The tutor's sealed tree, `tutor/v1-e2e`.
final RelayLayout tutorLayout = RelayLayout(
  'tutor/v1',
  clear: const [
    'meta',
    'rev',
    'migration',
    'requests/*/claim',
    'sessions/*/progress/rid',
  ],
  units: const {
    'live': {},
    'prefs/*': {},
    'stats/*': {},
    'presence/workers/*': {'beat'},
    'presence/clients/*': {'seen'},
    'uploads/*/*': {},
    'requests/*/req': {'created'},
    'requests/*/result': {'at'},
    'sessions/*/meta/*': {},
    'sessions/*/msgs/*': {},
    'sessions/*/receipts/*': {},
    'sessions/*/user/*': {},
    'sessions/*/progress/steps/*': {},
    'session_index/*': {},
    'subjects/*/meta': {},
    'subjects/*/plan': {},
    'subjects/*/cards': {},
    'subjects/*/concepts': {},
    'log/*/*': {},
    'feedback/*': {},
  },
);
