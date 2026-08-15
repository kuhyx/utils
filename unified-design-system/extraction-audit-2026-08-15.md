# Extraction audit — did we extract everything? (2026-08-15)

Answers "are all the components we actually use extracted?" across all three
shared packages, after Phases 1–3 shipped. Companion to `nielsen-audit.md`
(the grid) and `phase3-record.md` (Phase 3's verdicts).

**Short answer: everything is extracted now.** The audit found one leftover
donor copy and two genuinely-missed clusters; all three were resolved on
2026-08-15. The pre-existing extractions held up — no shipped component was a
false positive.

One repo is outstanding: **sims3-clone** still has its own RNG copy, skipped
because another session had uncommitted work in it.

## There is a fourth shared package

The phase briefs name three. There were four; this pass added two more, so
there are now six — one per stack per concern, all in the `kuhyx/utils`
monorepo:

| Package | Stack | Consumers |
| --- | --- | --- |
| `design_system` | Dart/Flutter | 6 repos |
| `gatelock` | Python/Tk | 4 guard apps (2 bumped) |
| `web_ui` | TS/React | dufs-cloud, awesome-mcp-explorer |
| **`sync_settings_ui`** | Dart/Flutter | todo, home_inventory, diet-guard, wake-alarm |
| `ts_core` *(new)* | TS, framework-free | konbini-67, iron-and-anvil, europe-county-map |
| `github_device_auth` *(new)* | Dart/Flutter | todo, home_inventory, diet-guard, wake-alarm |

`sync_settings_ui` (`backup_slot.dart`, `firebase_sync_controller.dart`,
`sync_settings_screen.dart`) changes the coverage answer for the whole sync
cluster — four of the five `SettingsScreen`s already delegate to it, so that
cluster is largely resolved rather than outstanding.

## Fixed in this pass

**billsplit's `_SectionHeader`** — a genuine leftover donor copy.
`billsplit/lib/ui/people_screen.dart` imported `design_system` while still
defining and using its own `_SectionHeader`. The shared `SectionHeader`'s
own doc names billsplit as a donor and sizes `defaultPadding` as
`fromLTRB(md, md, md, xs)` precisely to reproduce billsplit's `(16,16,16,4)`.
The union shipped; this donor was never deleted. Retired in
`testsAndMisc@54054e7`, verified geometrically identical.

(untools' `_SectionHeading`, the other named donor, *was* correctly deleted.)

## RESOLVED — `DeviceCodeDialog` + `GitHubDeviceAuth` ×4

**Extracted 2026-08-15** into `~/utils/github_device_auth` (v0.3.0). All four
apps migrated, local copies deleted, all four suites green, all four release
APKs installed on the phone.

The extraction found two real behaviours that existed in only one copy each,
and would have been *deleted* by a naive "take the canonical one" extraction:

- **diet-guard**: configurable `deviceCodeUrl`/`tokenUrl`. Its desktop web
  build must route through a local CORS proxy, because GitHub's device-flow
  endpoints send no CORS headers. Verified by `flutter build web` passing.
- **wake-alarm**: transient-network retry in `pollForToken`. GitHub can close
  the connection at the moment the user authorizes; without the retry an
  approved grant is lost.

Both are now in the shared package, so all four apps have both. Plus one bug
fixed for everyone: the dialog caught `on Exception`, which misses
`ArgumentError` and leaves it spinning forever — the same trap that killed
the Firebase sync tick in 2026-08.

**Lesson for the next extraction:** "byte-identical" applied to the *dialogs*,
not the *clients*. Diff every copy before picking a donor; the odd one out may
be the one that learned something.

## What the four GitHub copies looked like (historical)

| Repo | Client | Dialog |
| --- | --- | --- |
| todo | `lib/sync/github_device_auth.dart` (154) | `lib/ui/device_code_dialog.dart` (110, public) |
| home_inventory | same file, **byte-identical** (154) | — |
| diet-guard | `app/lib/services/…` (175, configurable URLs) | inline (~84) |
| wake-alarm | `phone_app/lib/services/…` (166, socket retry) | inline (~84, **byte-identical** to diet-guard's) |

`GitHubMirrorScreen` ×4 itself stays app-local — each copy carries the
"connecting here also triggers an actual sync" comment. Only the leaf
extracted.

## RESOLVED — `Clock` + mulberry32 RNG

**Extracted 2026-08-15** into `~/utils/ts_core` (`@kuhyx/ts-core` v0.1.0).
konbini-67, iron-and-anvil and europe-county-map migrated; all three green.

Deliberately its own package, not part of `web_ui`: that ships `tokens.css`
and React components, and making a game install a UI package to get a seeded
RNG is the coupling that causes vendoring in the first place.

The RNG exports **two** interfaces rather than one reconciled shape, because
the *sequence* is the contract — these repos guarantee "same seed → identical
world", so changing how many times a helper advances the generator re-rolls
every saved world. konbini-67 additionally keeps a local exclusive-max
`nextInt` adapter, verified identical over 10,500 draws.

`hotline3d` is deliberately NOT a consumer: its generator uses `%`/`Math.trunc`
where mulberry32 uses `>>>`, and measurably emits a different sequence.

**This forced all four game repos from npm to pnpm** — npm cannot install a
subdirectory of a git repo, so an npm repo is structurally locked out of every
shared package in this monorepo. sims3-clone is the one repo still pending:
another session had uncommitted work in it.

## Remaining true duplicates outside every package's remit

What is left after this pass. Neither is UI, so `web_ui` is still the wrong
home for both — `ts_core` took the TypeScript utilities, and the Dart one
belongs to `crdt_sync_dart`.

- **`_PrefsPersistence` ×3** — todo, home_inventory, diet-guard, all
  `implements LogPersistence`, all at the identical line number. Belongs to
  `crdt_sync_dart`'s remit.
- **mulberry32 RNG in `sims3-clone`** — the one consumer not yet migrated to
  `@kuhyx/ts-core`, skipped because another session had uncommitted work in
  that repo. Its interface (`next`/`int`/`pick`) maps onto `createSeededRng`
  directly; the migration is a seam file plus an npm→pnpm move.

## Correctly not extracted (name collisions)

Confirmed structurally disjoint — do not re-raise these:

- **`SettingsScreen` ×5** — four already delegate to `sync_settings_ui`;
  dufs-cloud's is a WebDAV connection form (`_url`/`_user`/`_pass`), not sync
  preferences.
- **`FilterSheet` ×3** — todo and home_inventory are Stateful, dufs-cloud is
  Stateless. The split alone rules out a common component.
- **`FilterBar`** — settled in `phase3-record.md`.
- **`EntryTile` ×2** — kuhylog log entries vs dufs-cloud `DirEntry` rows.
- **`HomeShell` ×2**, **`HomeScreen` ×2** — unrelated shells/screens.
- **`formatDuration` ×2** — personal-website takes a `Duration` (CV date
  range), dufs-cloud takes `ms: number` (media length). Disjoint signatures.
- **`ConfirmDialog`, `PromptDialog`, `StatBar`, `SummaryCards`** — single-use.

## Reviewed and judged benign

**leetcode-guard's five raw `tk.Button(` sites** (`_view.py:160,190,247`,
`_escape_flow.py:219`, `_study_strip.py:184`) persist despite the repo
importing `make_button`. All five sit inside the gate/lock-window path marked
do-not-touch, and each already applies the `fg=config.on_fill` contrast
discipline manually with an explanatory comment — the exact bug `make_button`'s
`variant` API exists to prevent. Worth migrating opportunistically; the
invariant is currently upheld.

## Not fully verified

`WrapperServer` ×4 (habit_stack 155 / home_inventory 217 / todo 223 /
diet-guard 254) was assessed from line counts and in-file architectural
comments, not a full body diff. If a hard verdict is wanted, that one still
needs opening.

## Phase 4 inputs (deferred, per the Q2 decision)

`personal-website`, `konbini-67`, `europe-county-map`, `sims3-clone`,
`steam-backlog-enforcer/web` and `iron-and-anvil` do not consume
`@kuhyx/web-ui`. All the `Clock`/RNG duplication lives entirely in this group.
`europe-county-map` and `iron-and-anvil` still define **zero** custom
properties, so they are token-adoption candidates independent of any component
work.
