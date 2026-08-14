/// The shared component layer for kuhy's Flutter apps.
///
/// `~/utils/unified-design-system/` froze the *token* layer as prose — one
/// palette, one spacing scale, one type scale — but shipped no importable
/// code, so every repo transcribed the table by hand and drifted. This
/// package is that same token set as Dart, plus the handful of widgets and
/// helpers that had each been reimplemented in three or more repos.
///
/// The tokens live *here*, not in a doc: a consumer that imports this package
/// cannot silently fall off the palette, because there is nothing local left
/// to edit.
library;

export 'src/confirm.dart';
export 'src/empty_state.dart';
export 'src/feedback.dart';
export 'src/section_header.dart';
export 'src/status_colors.dart';
export 'src/theme.dart';
export 'src/tokens.dart';
