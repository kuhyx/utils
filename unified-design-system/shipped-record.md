# Shipped record: palette drift, Phase 2, Phase 3

Companion to [`nielsen-audit.md`](nielsen-audit.md), which is the live audit
grid and the list of what is still open. This file is the history: work that
is **done**, kept because the *decisions* in it are load-bearing — the two
deliberate exceptions below exist so nobody "fixes" them back, and the
corrections found by measuring are why the current plan differs from the
original one.

Same convention as [`phase3-record.md`](phase3-record.md), which records the
web phase in the same way.

### Flutter — palette drift: DONE 2026-08-14

Standing decision: every app uses **exactly** the frozen palette; where copies
disagree, the most popular wins. That was unambiguous — 9 of 10 theme files
already used the gold `#B8862E` family. All four drifted repos are migrated.

| Repo | Drift that was fixed | How |
|---|---|---|
| `testsAndMisc/focus_owner` | **entirely off-palette**: cool `#5B9DD9` accent, `#1B1D21` field, `#D9776B` danger. Its doc comment claimed it matched the other `com.kuhy.*` apps; it did not. The same six constants were also **duplicated verbatim** in `main.dart:16-21` — the file said they had been "lifted out", but the originals were never deleted. | `theme.dart` now aliases `AppPalette`, so the ~80 call sites keep their names; both copies gone. Literals 15 → 2 (`Colors.transparent`). Verified on the Pixel 6a. |
| `kuhylog` | the only repo using `ColorScheme.fromSeed` (blue `#3B82F6`) — the opposite of what every other theme file documents. | `KuhylogTheme.of()` delegates to `buildLightTheme`/`buildDarkTheme`. Kept as a wrapper for its `visualDensity`, flat `cardTheme` and `scoreColor`. Literals 1 → 0. |
| `epopeja_karta` | `ColorScheme` inlined in `app.dart`, no `theme.dart`. | Imports **tokens only** — see below. Literals 9 → 0. |
| `billsplit` | `ColorScheme.fromSeed(Colors.teal)` plus 15 ad hoc literals that mostly bypassed the theme entirely. | `buildLightTheme()`; error family → `error`/`onError`/`errorContainer`, muted text → `onSurfaceVariant`. Literals 15 → 4. |
| `diet-guard`, `macro-cam` | scales drifted from the six-repo consensus | **still outstanding** — adopt `design_system` |

Two deliberate exceptions, so nobody "fixes" them back:

- **`epopeja_karta` adopts `AppPalette`, not `buildDarkTheme()`.** Its nine
  slots were already byte-identical to the frozen palette, so only the
  transcription was local. It is one dense screen with a test asserting
  nothing scrolls, and the shared theme's larger type scale plus
  `dividerTheme.space` overflows it by 34px. Typography there is a product
  decision; colour is the identity, and colour is what the system owns.
  Importing tokens leaves the rendered `ThemeData` identical, so the no-scroll
  test passes by construction rather than by hitting a pixel target.
- **`billsplit` keeps its four category-dot colours** (`deepOrange`/`amber`/
  `blueGrey`/`teal` for alcohol/mixer/deposit/other). They encode *category
  identity*, not a theme role, and a single-accent system has no four distinct
  hues to lend. Folding them into `primary`/`secondary`/`tertiary` would make
  the categories stop being distinguishable, which is their only job. **This
  is the open categorical-ramp question** — the design system currently has no
  answer for "N mutually distinguishable hues", and it needs one before any
  chart, tag or category UI can be built on it.

### Remaining Flutter adopters

`home_inventory`, `dufs-cloud`, `habit_stack`, `diet-guard`, `macro-cam`,
`wake-alarm/phone_app`. Each drops its local `theme.dart` for the tag-pinned
dep, as todo, untools, focus_owner, kuhylog, epopeja_karta and billsplit now
do. These six were never off-palette — they transcribe the right values by
hand — so this is duplication cleanup, not a visual fix.

### Phase 2 — Python/Tk (`~/utils/gatelock`), SHIPPED (gatelock 0.5.0)

> **Status: done.** `make_button`, `heading`/`row`, `ScrollableSurface` and
> `WidgetGroup` all ship in gatelock 0.5.0 (`c963cd8`, `d82107a`, `d25f288`);
> diet-guard and leetcode-guard are the migrated proof consumers.
> screen-locker (v0.4.0) and wake-alarm (v0.4.1) keep local fan-out copies
> **by design** — only two consumers were bumped to avoid restarting live
> systemd services. That asymmetry is not a regression; do not "fix" it.
> Everything below this line is the original plan, kept as the record of why.

Not a new package: gatelock already owns the tokens (`LockConfig`), the Tk
plumbing and 4 consumers. Add composite widgets, which is where its scope
currently stops.

1. `widgets.py::make_button` — canonical is diet-guard's
   `_gatelock_buttons.py::make_button`, whose `variant` API picks text color
   *from* the fill and so structurally prevents the `fg`-vs-`on_fill` contrast
   bug. leetcode-guard's `_button` (no `<Return>` binding) and screen-locker's
   inline `tk.Button` are the regressions being retired.
2. `widgets.py::heading()` / `row()` — from `leetcode_guard/_status_sections.py`.
3. **Export the existing `ScrollableSurface`** and delete
   `leetcode_guard/status_view.py::_scrollable`, a hand-rolled reimplementation
   that lost `takefocus` and the focus ring. Straight accessibility repair.
4. `widget_group.py::WidgetGroup` — the per-output fan-out reimplemented 4×
   (~916 lines: screen-locker 173, leetcode-guard 105, diet-guard 309,
   wake-alarm 329). Highest line-count win on this stack.

Proof consumers: `diet-guard` and `leetcode-guard` (donor and worst offender).
Bump **only those two**; leave screen-locker and wake-alarm on their current
pin — Phase 2 is additive, and restarting live services is blast radius for no
gain.

> **Verification gate — non-negotiable.** gatelock backs live systemd
> services. After any change: `/usr/bin/python3 -c "import gatelock"` against
> the real interpreter, not a dev venv. Do not touch the gate window's grab
> path. Then launch each gate under `xvfb-run -s "-screen 0 1366x768x24"` and
> confirm buttons render and **`<Return>` activates** them.

### Phase 3 — TypeScript (`~/utils/web_ui`), SHIPPED (web_ui-v0.3.1)

> **Status: done** — see `phase3-record.md` for what shipped and, importantly,
> why `FilterBar` was *not* extracted (a name collision, not a duplicate).
> Both proof consumers (dufs-cloud, awesome-mcp-explorer) are migrated.
> Everything below this line is the original plan, kept as the record of why.

Lowest confirmed duplication (2 components, 2 repos) and the only stack needing
a brand-new consumption mechanism, so it carries the worst effort-to-payoff
ratio — sequenced last on purpose.

1. `tokens.css` — one `:root` block. Fixes the worst fork found: **7 repos
   define 7 different vocabularies for the same palette** (`--surface-1` vs
   `--panel` vs `--card`; `--text` vs `--ink` vs `--fg` vs `--bone`; spacing as
   `--space-N` vs `--sp-N` vs `--sp-xs`). europe-county-map and iron-and-anvil
   have **zero** custom properties.
2. `RangeSlider` — canonical is dufs-cloud's, whose pure
   `fractionFromPointer(rect, clientX)` is testable without layout (jsdom has
   none). awesome-mcp-explorer's copy has drifted 196 lines.
3. `FilterBar` + `filter-sort.ts` — reconcile dufs-cloud (174) vs
   awesome-mcp-explorer (225).

**Consumption mechanism (decided 2026-08-14):** a git dep
`"@kuhyx/web-ui": "github:kuhyx/utils#web_ui-v0.1.0"`, matching the Dart/Python
tag convention rather than introducing npm workspaces — but shipping a
**prebuilt `dist/`** (tsc → ESM + `.d.ts`) committed in the tag. Raw `.tsx` in
`node_modules` would need per-repo bundler config, since Vite does not
transpile dependencies by default; a committed `dist/` keeps consumers at zero
config.

Proof consumers: `dufs-cloud` and `awesome-mcp-explorer`.
