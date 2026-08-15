# Nielsen coverage audit

Jakob Nielsen's ["10 GUI Design Elements Build Every User
Interface"](https://jakobnielsenphd.substack.com/p/gui-widgets) argues that
essentially every UI is assembled from ~10 standardized elements, and that the
value comes from *reusing* those conventions rather than re-inventing them.
Re-implementing the same button in eight repos is the private version of the
convention erosion he describes.

This file is the **audit grid**, not a build list. Shipping a widget nobody
imports is the failure mode to avoid — 183 imported agent definitions were
invoked zero times in 432 sessions. A component gets built only where **two or
more repos already contain a structurally similar implementation**.

Written 2026-08-14, alongside `design_system` v0.1.0.

**Phase 3 (web, `@kuhyx/web-ui`) is recorded in `phase3-record.md`** — including
why `FilterBar` was *not* extracted (structurally disjoint despite the shared
name) and the new categorical ramp. Read it before re-proposing any web
component.

## Scope

Fourteen Flutter repos, seven web repos, four Python/Tk guard apps. Out of
scope, verified rather than assumed: Unity (zero `.uxml`/`.uss` files exist
anywhere), games (their repeated identifiers are game constants like
`FORGE_MAX_C`, not UI), and the locker gate windows (their X-grab/input-hijack
invariants make the *window* non-reusable, though its leaf widgets are fair
game).

`~/testsAndMisc/pomodoro_app` and `horatio` no longer exist. **`workout_app`
does not exist either** — it is named in the source plan and in several skill
docs, but no directory under `~` matches `*workout*`. Anything citing it as a
consumer is stale.

## The grid

| # | Nielsen element | Flutter | Web | Python/Tk |
|---|---|---|---|---|
| 1 | Buttons | ⚠️ themed only | ❌ 7 vocabularies | ⚠️ 4 factories, see Phase 2 |
| 2 | Input fields / forms | ✅ `inputDecorationTheme` | ❌ | ⚠️ |
| 3 | Menus | ❌ not specced | ❌ | ❌ |
| 4 | Links | ❌ not specced | ❌ | n/a |
| 5 | Dialogs | ✅ `confirmDestructive()` | ❌ | ⚠️ |
| 6 | Alerts / notifications | ✅ `showToast`/`showError` | ❌ | ❌ |
| 7 | Icons | ❌ not specced | ❌ | ❌ |
| 8 | Checkboxes / radio buttons | ⚠️ themed only | ❌ | ❌ |
| 9 | Tabs | ❌ not specced | ❌ | ❌ |
| 10 | Search | ❌ not specced | ⚠️ `FilterBar` ×2 | n/a |

`components.html` specs 9 components but says nothing about **menus, links,
icons, radio buttons, tabs, or search** — six of Nielsen's ten. That is the
documentation gap; whether any of them deserves *code* still depends on the
two-repo extraction criterion, which most of them currently fail.

## What v0.1.0 closed

| Export | Replaced |
|---|---|
| `AppPalette` + scales | 10 divergent `theme.dart` copies; ~318 raw color literals |
| `buildLightTheme` / `buildDarkTheme` | the same, per repo |
| `AppStatusColors` | 4 hand-rolled `ThemeExtension`s with inconsistent fields |
| `confirmDestructive()` | ~35 inlined `AlertDialog`s |
| `showToast` / `showError` | ~38 raw `SnackBar` sites, zero helpers |
| `EmptyState` | 4 variants, one reusable |
| `SectionHeader` | 3 near-identical private widgets |

Proof consumers `todo` and `untools` are migrated, verified and pushed.

### Which exports have a live consumer

An extracted component with no importer is the failure mode this audit
exists to prevent, so the honest status per export:

| Export | Live consumers |
|---|---|
| tokens, palette, themes | todo, untools |
| `confirmDestructive` | todo (2 sites) |
| `showToast` / `showError` | todo (3 sites) |
| `SectionHeader` | untools (2 sites) |
| `EmptyState` | **none yet** — donor is home_inventory (3 sites), unmigrated |
| `AppStatusColors` | **none yet** — 4 donors, all unmigrated |

Palette/token consumers beyond the two proof apps, added the same day:
`focus_owner`, `kuhylog`, `epopeja_karta` (tokens only) and `billsplit`.

The last two ship ahead of their consumers. That is defensible (both have
real donors waiting, and `AppStatusColors` must exist for `showError` to read
the danger hue off the theme) but it is not *validated*, and it should be
called that way until home_inventory or one of the status-color donors
migrates.

### Corrections to the original plan, found by measuring

The plan's figures were mostly right but three were not, and the difference
changes what is worth doing next:

- **The "343 raw literals" are not spread through call sites.** They are
  concentrated in the hand-copied theme files. todo had 35, *all 35* inside
  `theme.dart`; untools had 36, of which 35 were in `theme.dart` and the last
  was `Colors.transparent` in `keyboard.dart` — a sentinel, not a palette
  value. Deleting the theme file removes essentially all of them. There was no
  call-site sweep to do in either proof consumer, and the same is true of
  home_inventory, habit_stack, diet-guard, wake-alarm, macro-cam and kuhylog,
  which all have **zero** literals outside their token file. The repos with
  genuine call-site leakage are `billsplit` (16, all ad hoc `Colors.red`/
  `teal`/`black54`), `epopeja_karta` (14, palette inlined in `app.dart`) and
  `focus_owner` (8).
- **There are 4 `AppStatusColors`, not 5**, and they disagree about their own
  shape: home_inventory and diet-guard have `success` + `warning`, habit_stack
  has `success` only, wake-alarm has both; home_inventory and habit_stack ship
  `light` *and* `dark` statics, the other two `dark` only. The package's
  version is a superset (`success`/`warning`/`danger`/`info`/`onStatus`), so
  every consumer can adopt it without losing a field.
- **There are 3 section headers, not 5**, and no `_SectionLabel` exists. Two
  agreed on `titleMedium` and were reconciled into `SectionHeader`;
  `epopeja_karta`'s is a *different element* — `labelSmall` + primary color +
  letter-spacing, i.e. an eyebrow, not a section title. It was deliberately
  not folded in.

## Deferred clusters

Actionable later; each line is repo + path + size, so none of this needs
rediscovering.

### Flutter — large reconciliations

| Cluster | Where | Size |
|---|---|---|
| `GitHubMirrorScreen` ×5 | todo, diet-guard, +3 | ~1551 lines, 586 differing between two copies |
| `SettingsScreen` ×6 | fleet-wide | — |
| List tiles | ~20 classes fleet-wide | — |
| Filter sheets | todo, dufs-cloud, +1 | **name collision, not duplicates** — dufs-cloud's uses no chips at all; judge structurally |
| Steppers, badges | fleet-wide | — |

The five `GitHubMirrorScreen` copies each carry a near-verbatim "kept
app-local rather than folded into `sync_settings_ui`" comment. That decision
deserves revisiting **on its own**, not smuggled into a component extraction.

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

## Standing risks

- **Version churn.** Each new tag needs a `pubspec.yaml` bump in every
  consumer. `habit_stack` is already **7 minor versions stale** on `crdt_sync`
  (v0.3.0 vs v0.10.0); the same drift will hit this package.
- **Reconciliation is judgement.** Where copies diverged, a "best-of" choice
  can regress a consumer that depended on its local variant. Migrating proof
  consumers first exists to surface that early.
