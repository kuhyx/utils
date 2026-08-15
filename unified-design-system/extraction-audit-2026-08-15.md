# Extraction audit — did we extract everything? (2026-08-15)

Answers "are all the components we actually use extracted?" across all three
shared packages, after Phases 1–3 shipped. Companion to `nielsen-audit.md`
(the grid) and `phase3-record.md` (Phase 3's verdicts).

**Short answer: yes, with one leftover — now fixed — and one clear miss.**

The three packages' extractions hold up. No shipped component turned out to be
a false positive, and the reverse check (did the donor copies actually get
deleted?) is clean except for one case.

## There is a fourth shared package

The phase briefs name three. There are four:

| Package | Stack | Consumers |
| --- | --- | --- |
| `design_system` | Dart/Flutter | 6 repos |
| `gatelock` | Python/Tk | 4 guard apps (2 bumped) |
| `web_ui` | TS/React | dufs-cloud, awesome-mcp-explorer |
| **`sync_settings_ui`** | Dart/Flutter | todo, home_inventory, diet-guard, wake-alarm |

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

## The one clear miss — `DeviceCodeDialog` ×3

The strongest finding. A modal showing a GitHub device-flow user code:
copies to clipboard, launches the verification URL, polls for the token,
pops with it or renders an error.

| Repo | Path | Lines |
| --- | --- | --- |
| todo | `lib/ui/device_code_dialog.dart` | 110 (public) |
| wake-alarm | `phone_app/lib/screens/github_mirror_screen.dart:157-240` | ~84 (private) |
| diet-guard | `app/lib/screens/github_mirror_screen.dart:398-481` | ~84 (private) |

**The wake-alarm and diet-guard copies are byte-for-byte identical** (`diff`
returns empty). todo's differs only by being public/keyed with doc comments.
Same domain types (`DeviceCodeResponse`, `GitHubDeviceAuth`), same props, same
`String? _error` state, same `initState`→`_poll` lifecycle.

**Belongs in `sync_settings_ui`, not `design_system`** — it depends on GitHub
auth types, so it is not a generic widget. Not yet extracted.

Note this is a *leaf* of the `GitHubMirrorScreen` ×4 cluster, which is
deliberately app-local (each copy carries the "connecting here also triggers
an actual sync" comment). The screen stays local; the dialog need not.

## True duplicates outside every package's remit

Real duplication, but none of it is UI, so no existing package owns it.
**These are not a reason to widen `web_ui`'s remit** — it is a UI package, and
the games were explicitly out of Phase 3 scope. A separate shared utility
module would be the vehicle, in a future phase.

- **`_PrefsPersistence` ×3** — todo, home_inventory, diet-guard, all
  `implements LogPersistence`, all at the identical line number. Belongs to
  `crdt_sync_dart`'s remit.
- **`Clock` / `createRealClock` / `createManualClock` ×2** — konbini-67 (59
  lines) and iron-and-anvil (49). Same interface, same `realClock` shared
  instance with the same rationale, doc comments near-verbatim.
- **mulberry32 seeded RNG ×4** — konbini-67, sims3-clone, europe-county-map,
  hotline3d. Identical `0x6d2b79f5` core in all four, but the *interfaces*
  genuinely differ (closure-returning-methods vs mutable-state-plus-free-
  functions; `float`/`next` naming; `chance` in only one). Extractable, but
  it is an API reconciliation, not a lift-and-shift.

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
