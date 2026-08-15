# Phase 3 record — `~/utils/web_ui` (`@kuhyx/web-ui`)

The web counterpart to Phase 1's Dart `design_system`. Companion to
`nielsen-audit.md`, which holds the grid and the deferred clusters.

Shipped as `web_ui-v0.3.0`, consumed by **dufs-cloud** and
**awesome-mcp-explorer**.

## What shipped

| Item | Notes |
| --- | --- |
| `tokens.css` | Full palette, spacing, radius, type, shadow tiers, focus ring, and the global `:focus-visible` rule. |
| `RangeSlider` | Reconciled from the two drifted copies; keyboard-operable. |
| `quantile.ts` | `nth`, `clamp01`, `quantileValue`, `valueQuantile`, `fractionFromPointer`. |
| `fuzzyMatch` | Was `fuzzyMatch` in dufs-cloud and `matchesFuzzy` in amx. |
| Categorical ramp | `--cat-1…6`; see `tokens.md`. New token group, see below. |

## FilterBar was NOT extracted — and should not be

The phase brief listed `FilterBar` + `filter-sort.ts` as the third component,
to be "reconciled" between dufs-cloud (174 lines) and awesome-mcp-explorer
(225). Inspection says they are a **name collision, not a duplicate** — exactly
the Phase 1 trap the brief itself warns about, one level deeper than the three
`FilterSheet`s.

They share a name and nothing else:

| | dufs-cloud | awesome-mcp-explorer |
| --- | --- | --- |
| Shape | horizontal `<div class="filterbar">` strip | vertical `<aside class="filters">` sidebar |
| Controls | search input, `<select>`s, sort key + direction | tri-state chip pickers, no search, no sort |
| Domain | files (`DirEntry` + `MetaIndex`) | MCP servers (`Server`) |
| Props | `onFilter` + `onSort` | one `onChange` |
| `FilterState` | `type`/`extIncludes`/`minSize`/`minDurationMs`/`minPixels` | `languages`/`scope`/`os`/`foss`/`cost`/`grades` |
| `SortKey` | 9 file keys | disjoint server keys |

`applyFilterSort` differs in arity and parameter types. Extracting a component
over this would mean inventing a generic that neither caller wants, then
threading both vocabularies through it — the "shipping a widget nobody imports"
failure mode, with a forced abstraction on top.

What *was* genuinely duplicated inside those files was extracted: the fuzzy
subsequence matcher (identical algorithm, renamed identifiers) and the whole
`quantile.ts` module (near-verbatim, comments aside).

**Do not re-raise FilterBar as an extraction candidate** without new evidence —
specifically, a third repo whose filter surface is structurally like one of
these two. A shared *sort-direction toggle* or *filter-chip* is a plausible
future extraction; the bar itself is not.

`passesTri`/`TriSelect` was checked as a possible third duplicate: dufs-cloud
carries `extIncludes`/`extExcludes` in its `ExtensionPicker`, but the logic is
inline and file-extension-specific, not a shared generic. One repo is not two,
so it stays in amx.

## The categorical ramp (new)

The brief flagged that the design system has one accent and therefore no answer
for "N mutually distinguishable hues", and said to raise it rather than invent
one inline. It was raised; the decision was to **design a real ramp** rather
than map grades onto `success`/`warning`/`danger` (which would have collapsed
six ordinal steps into three and made A and B identical).

Six colours, chosen by search under measured constraints, documented in
`tokens.md` and re-checkable with `scripts/ramp_check.py` (exits non-zero on a
regression). The binding constraint turned out to be theme independence: a
colour readable on both `ink` and `paper` must sit in L\* 44–59, which is why
the ramp is mid-toned throughout. A seventh hue is not available at ΔE 20 — the
best candidate reaches 17.9.

amx's grades now map onto it. **This changed those colours visibly**, and for
the better: the old hand-picked A/B pair (`#2f8f5b` green vs `#4f8f2f` olive)
was nearly indistinguishable under deuteranopia.

## Follow-ups

1. **Dart side does not have the ramp.** `tokens.md` is the source of truth for
   both stacks and now documents `cat-1…6`, but `~/utils/design_system` ships
   only the original palette. A `design_system` bump should add it, so the
   "same hex values everywhere" invariant holds. Deliberately not done here:
   Phase 1 is tagged with six consumers, and that retag is its own change.
2. **Python/Tk side** likewise has no ramp (no consumer needs one yet).
3. **npm cannot consume this package.** `utils` has no root `package.json`, and
   npm's `github:` shorthand has no subdirectory syntax — it clones the root and
   fails with `ENOENT` (verified, npm 11.16). pnpm's `&path:/web_ui` works, so
   both consumers are pnpm. A future npm-only consumer needs either its own repo
   or a published tarball.

## Verification performed

- `pnpm test` + 100% coverage in all three repos (web_ui 84, amx 405, dufs 224).
- Built bundles grepped: shared tokens present, every bespoke value absent —
  definitions *and* `var()` references, since checking only definitions lets a
  shadowed token survive.
- Real headless Chrome at 1366x768 and 1024x600: `scrollWidth <= innerWidth`,
  and `:focus-visible` computed as `2px solid rgb(184,134,46)` after a real Tab
  (a programmatic `.focus()` does not match `:focus-visible` and will report no
  ring even when one is correctly styled).
- dufs-cloud checked against a live `dufs` backend, since a static file server
  answers `501` to `PROPFIND` and the app never renders its filter bar.

## The bug jsdom could not catch

The first cut of the keyboard support stepped by *array index*. Every unit test
passed, on an evenly spaced ten-value fixture. In the browser the arrow keys did
nothing: ~1500 of amx's ~2981 star values are `0`, so a step inside that run
moved the index and left the value — and therefore the thumb, the readout and
the filter — exactly where it was.

`steppedValue` now walks to the next *distinct* value. The lesson is about
fixtures, not about arrows: an evenly-spaced fixture is not a distribution, and
the component's whole reason for existing is that real distributions are lumpy.
