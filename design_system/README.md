# design_system

The shared Flutter component layer for kuhy's apps.

`~/utils/unified-design-system/` froze the **token** layer — one palette, one
spacing scale, one type scale — but it is documentation only: 1220 lines of
prose and annotated HTML, zero importable code. Every repo transcribed the
token table by hand, and then drifted from it.

This package is that same token set as Dart, plus the handful of widgets that
had each been reimplemented in three or more repos. **The components own the
tokens**: a consumer that depends on this package has nothing local left to
edit, so the palette is enforced by the compiler and the package manager
instead of by prose plus discipline.

## Consuming it

Tag-pinned git dependency, matching the convention `sync_settings_ui` and
`crdt_sync_dart` already use:

```yaml
dependencies:
  design_system:
    git:
      url: https://github.com/kuhyx/utils
      ref: design_system-v0.1.0
      path: design_system
```

Then delete the repo's local `lib/ui/theme.dart` and import the package:

```dart
import 'package:design_system/design_system.dart';

MaterialApp(
  theme: buildLightTheme(),
  darkTheme: buildDarkTheme(),
  // ...
);
```

## What's in it

| Export | Replaces |
|---|---|
| `AppPalette` | ~318 raw `Color(0x…)` literals, almost all inside hand-copied theme files |
| `AppSpacing` / `AppRadius` / `AppTextSize` | the six-repo consensus scales, transcribed per repo |
| `buildLightTheme()` / `buildDarkTheme()` | 10 divergent `theme.dart` copies (2 byte-identical, 8 drifted) |
| `AppStatusColors` | 4 hand-rolled `ThemeExtension`s with inconsistent field sets |
| `confirmDestructive()` | ~35 inlined `AlertDialog`s |
| `showToast()` / `showError()` | ~38 raw `SnackBar` sites and zero helpers |
| `EmptyState` | 4 variants, only one of them reusable |
| `SectionHeader` | 3 near-identical private widgets |

### Why the scales are what they are

The values are the six-repo consensus — todo, home_inventory, dufs-cloud,
habit_stack, and untools all shipped byte-identical copies — which is also
exactly what `unified-design-system/tokens.md` specifies. Repos that had
drifted (diet-guard, macro-cam) are corrected *to* this package, not the
other way round.

### Why explicit `ColorScheme`s, never `fromSeed`

The palette is hand-picked to hit specific contrast ratios. A seeded scheme
silently replaces those values with algorithmically derived ones. The
`secondary`/`tertiary` slots are set explicitly for the same reason: without
them, widgets that reach for `secondaryContainer` (e.g. `SegmentedButton`'s
selected segment) fall back to stock Material teal — confirmed on-device.

## Development

```bash
flutter analyze                                  # must be clean
dart format lib test
flutter test --coverage
scripts/check_coverage.sh coverage/lcov.info 100 # 100% line coverage, gated
```

Coverage is a **gate, not a convention**: this ships as a 100%-covered shared
package by requirement. The gate runs on pre-push.
