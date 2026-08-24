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

### Shipped work

Palette drift, Phase 2 (Python/Tk) and Phase 3 (TypeScript) are all done. The
decisions behind them — including two deliberate exceptions that must not be
"corrected" back, and the remaining Flutter adopters — are in
[`shipped-record.md`](shipped-record.md).

## Standing risks

- **Version churn.** Each new tag needs a `pubspec.yaml` bump in every
  consumer. `habit_stack` is already **7 minor versions stale** on `crdt_sync`
  (v0.3.0 vs v0.10.0); the same drift will hit this package.
- **Reconciliation is judgement.** Where copies diverged, a "best-of" choice
  can regress a consumer that depended on its local variant. Migrating proof
  consumers first exists to surface that early.
