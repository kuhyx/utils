# unified-design-system

The concrete, frozen design tokens (colors, spacing, type, radius, shadow
policy) that implement `safe-design-rules`' 28 abstract rules identically
across every one of kuhy's repos — Flutter, web/React, and Python/Tkinter.
One palette everywhere (including Flutter launcher-icon glyphs), not just
shared rules. Use whenever building or fixing UI in any of kuhy's repos —
this is what a design audit's violations should be fixed *against*, and what
new UI should be built from instead of inventing new values. Full frozen
value table in [`DOCS-tokens.md`](DOCS-tokens.md); annotated component references in
[`components.html`](components.html) (9 components: Button/Card/Input/Chip/
Dialog/Switch/Divider/Checkbox/SnackBar) and [`button.html`](button.html)
(the earlier single-component exemplar that set the doc format).

Read `DOCS-tokens.md` for the full frozen value table before touching any
theme/CSS/style file.

## Why one palette, not per-app branding

Apps are visually unified down to the exact hex values, not just the same
rules with different accents. This also means the Flutter launcher-icon
family (the `app-icon` skill/generator) uses the same accent for every app's
glyph — apps are distinguished by glyph shape, not color.

## Per-stack implementation pattern

### Flutter

Build `ThemeData` from **explicit** `ColorScheme.dark(...)`/`.light(...)`
using the exact hex values in `DOCS-tokens.md` — not `ColorScheme.fromSeed`, which
algorithmically derives tones and won't reproduce hand-picked values. Add:

- A `ThemeExtension` for roles M3 doesn't have (success/warning — `error` is
  already `danger`), e.g. `AppStatusColors(success:, warning:)`. Only add
  this if the app actually has success/warning status indicators — grep for
  existing `Colors.green`/`Colors.orange`-style usage first; don't add it
  speculatively (it becomes untested dead code otherwise).
- `AppSpacing` / `AppRadius` / `AppTextSize` static const classes mirroring
  the scales in `DOCS-tokens.md`.
- Wire every screen through `Theme.of(context)` — the dominant violation
  across every Flutter audit was raw `Colors.*` literals bypassing an
  existing (or newly added) theme. Grep for `Colors\.` / `Color(0x` after
  wiring the theme and route every hit through a theme role.

```dart
ThemeData buildTheme() => ThemeData(
  useMaterial3: true,
  colorScheme: const ColorScheme.dark(
    surface: Color(0xFF211D1B),        // ink
    surfaceContainerHighest: Color(0xFF38312E), // ink-raised-2
    onSurface: Color(0xFFECEAE9),      // text-on-dark
    onSurfaceVariant: Color(0xFFAAA09A), // muted-on-dark
    outline: Color(0xFF463E3A),        // line-dark
    primary: Color(0xFFB8862E),        // accent
    onPrimary: Color(0xFF211D1B),      // on-fill — NOT text-on-dark, see below
    error: Color(0xFFE2585F),          // danger
    onError: Color(0xFF211D1B),        // on-fill
  ),
  extensions: const [AppStatusColors(
    success: Color(0xFF8A9A3C),
    onSuccess: Color(0xFF211D1B),      // on-fill
    warning: Color(0xFFE0A63C),
    onWarning: Color(0xFF211D1B),      // on-fill
  )],
);
```

`onPrimary`/`onError`/`onSuccess`/`onWarning` are all `on-fill` (`#211D1B`,
dark), never `onSurface`'s near-white — see `DOCS-tokens.md`'s `on-fill` entry:
every filled semantic color under-contrasts with near-white text.

### Web (CSS custom properties)

One `:root` block (plus a light/dark override block as needed) with these
variable names — kept identical across repos so the vocabulary transfers:

```css
:root {
  --bg: #211d1b; --surface-1: #2b2624; --surface-2: #38312e;
  --border: #463e3a; --text: #eceae9; --text-muted: #aaa09a;
  --accent: #b8862e; --success: #8a9a3c; --warning: #e0a63c; --danger: #e2585f;
  --on-fill: #211d1b;   /* text/icons ON a filled accent/success/warning/danger surface */
  --on-scrim: #eceae9;  /* text/icons on a dark translucent overlay/backdrop — fixed, not theme-tied */
  --radius-sm: 8px; --radius-md: 12px; --radius-lg: 16px;
  --space-1: 4px; --space-2: 8px; --space-3: 16px; --space-4: 24px;
  --space-5: 32px; --space-6: 48px;
  --font-sans: -apple-system, "Segoe UI", Roboto, system-ui, sans-serif;
  --font-mono: ui-monospace, "Cascadia Code", monospace;
}
@media (prefers-color-scheme: light) {
  :root {
    --bg: #f6f4f3; --surface-1: #fcfbfb; --surface-2: #fcfbfb;
    --border: #e0dad7; --text: #211d1b; --text-muted: #70625b;
    /* --on-fill / --on-scrim stay fixed — the fills and the scrim don't change with page theme */
  }
}
body { font-size: 16px; font-family: var(--font-sans); }
button.primary { background: var(--accent); color: var(--on-fill); }
```

Don't reach for a single "on-accent" variable for both cases (an earlier
dufs-cloud draft did, and it broke the moment the accent went from blue to
gold): a filled button needs `--on-fill` (dark), a caption over a photo-tile
scrim needs `--on-scrim` (near-white) — same-looking near-white token, wrong
one silently fails contrast on fills.

Every hardcoded color/spacing/radius/shadow value in component CSS should
route through one of these variables. No `#fff`/`#000`/`rgba(0,0,0,…)`
literals — use `var(--text)`/`var(--bg)` or an `ink`-tinted rgba.

### Python/Tkinter

No `ttk.Style()` in any of these apps currently — introduce (or, for the
screen-locker/wake_alarm/diet_guard family, extend) a shared constants
module/dataclass with the same token names, and have every `tk.Label`/
`tk.Button`/`tk.Frame` read from it instead of inline hex literals:

```python
@dataclass(frozen=True)
class Tokens:
    bg: str = "#211D1B"
    fg: str = "#ECEAE9"
    muted: str = "#AAA09A"
    field_bg: str = "#2B2624"
    accent: str = "#B8862E"
    success: str = "#8A9A3C"
    warning: str = "#E0A63C"
    danger: str = "#E2585F"
    on_fill: str = "#211D1B"  # text on an accent/success/warning/danger bg — NOT fg
    font_family: str = "Arial"
```

A shared `_button(bg=...)` helper that always sets `fg=self._colors.fg` is
the exact bug this caught: `fg` (near-white) is correct when `bg` is
`field_bg`/`bg` (a dark neutral surface), but any button whose `bg` is
`accent`/`success`/`warning`/`danger` needs `fg=self._colors.on_fill`
instead — pick `fg` from `bg`, don't hardcode it per call site.

For screen-locker/wake_alarm/diet_guard specifically: this lives on
`gatelock.LockConfig` (the shared token source already vendored in this same
`~/utils` monorepo, see [`../gatelock/`](../gatelock/)) rather than a
per-repo duplicate, since all three already depend on it. Extending
`LockConfig` requires production verification
(`/usr/bin/python3 -c "import gatelock"`) since it backs 3 live systemd
services — a dev-venv-only check is not sufficient.

## Pointer-free + small-screen

The rules are in [`DOCS-operability.md`](DOCS-operability.md); the per-stack code that
satisfies them — Flutter, web and Python/Tkinter — is in
[`DOCS-operability-patterns.md`](DOCS-operability-patterns.md).

## Do NOT

- Don't use `ColorScheme.fromSeed` for the unified palette — it can't
  reproduce hand-picked hex values exactly.
- Don't pass a positive font size to Tk — that's points, ~37% oversized.
- Don't make long-press, hover, or drag the only route to an action.
- Don't set `highlightthickness=0` on anything focusable, or set
  `highlightbackground` when you meant `highlightcolor`.
- Don't centre-anchor content that can overflow — it clips symmetrically, taking
  the header and the submit button with it.
- Don't tune a layout against a 1080p screen, and don't test responsiveness only
  at phone-portrait sizes; neither exercises 1366x768 or 1024x600.
- Don't add shadows to dark surfaces, or mix shadow + border depth on the
  same element (see `DOCS-tokens.md`'s shadow policy).
- Don't invent a new spacing/radius/font value outside the scales in
  `DOCS-tokens.md` — round to the nearest step instead.
- Don't add a `ThemeExtension`/status-color role speculatively — check the
  app actually uses that status (success/warning/etc.) before adding it.
- Don't touch `../gatelock` without the production-path verification above;
  a broken import there takes down 3 services at once.
