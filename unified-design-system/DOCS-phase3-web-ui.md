Implement Phase 3 of the shared component work: create `~/utils/web_ui/` (TypeScript) and migrate two proof consumers onto it. Treat this as `override` on the spec gate — the spec is below, it is complete, and I do not want a round of questions before you start.

**Goal.** Seven web repos define seven different vocabularies for the same palette: `--surface-1` vs `--panel` vs `--card`; `--text` vs `--ink` vs `--fg` vs `--bone`; spacing as `--space-N` vs `--sp-N` vs `--sp-xs`. Two of them additionally carry the same two components, drifted. Give the web stack the token + component layer that Dart already has.

**Build these three:**

1. `tokens.css` — one `:root` block using the canonical variable names from `~/utils/unified-design-system/README.md` and `tokens.md`. The palette is frozen: ink `#211D1B`, ink-raised-1 `#2B2624`, ink-raised-2 `#38312E`, line-dark `#463E3A`, text-on-dark `#ECEAE9`, muted-on-dark `#AAA09A`, paper `#F6F4F3`, paper-raised `#FCFBFB`, line-light `#E0DAD7`, muted-on-light `#70625B`, accent `#B8862E`, success `#8A9A3C`, warning `#E0A63C`, danger `#E2585F`, on-fill `#211D1B`. Spacing 4/8/16/24/32/48, radius 8/12/16, type 12/14/16/20/24/32. Do not invent new values; these are the same numbers `~/utils/design_system` ships for Dart.
2. `RangeSlider` — canonical is **dufs-cloud's**, whose pure `fractionFromPointer(rect, clientX)` is testable without layout (jsdom has none). awesome-mcp-explorer's copy has drifted 196 lines. Keep the pure function pure; that is the whole reason this one is the donor.
3. `FilterBar` + `filter-sort.ts` — reconcile dufs-cloud (174 lines) vs awesome-mcp-explorer (225).

**Consumption mechanism — already decided, do not re-litigate.** A git dep `"@kuhyx/web-ui": "github:kuhyx/utils#web_ui-v0.1.0"`, matching the Dart/Python tag convention rather than introducing npm workspaces. **Ship a prebuilt `dist/` (tsc → ESM + `.d.ts`) committed in the tag.** Raw `.tsx` in `node_modules` would need per-repo bundler config, because Vite does not transpile dependencies by default; a committed `dist/` keeps consumers at zero config. This is the only stack with no existing precedent — verified: no `workspaces` key and no `file:`/`link:`/`github:kuhyx` dep anywhere — so the mechanism is the risky part, not the components.

**Proof consumers: `dufs-cloud` and `awesome-mcp-explorer`** — the only two with confirmed shared components. Migrate both; do not stop at one.

**Extraction criterion.** Build a component only where two or more repos already contain a structurally similar implementation. Nielsen's ten elements are the audit grid, not a build list — shipping a widget nobody imports is the failure mode to avoid. Two traps from Phase 1: a **name collision is not a duplicate** (judge structurally — the three `FilterSheet`s share a name but one uses no chips at all), and when you extract something, **retire the donor copies in the same pass**, or you have shipped a duplicate rather than removed one.

**An open question you will hit.** The design system has one accent and therefore no answer for "N mutually distinguishable hues" — a categorical ramp for charts, tags and category dots. billsplit's four category colours were deliberately left unmapped for this reason. If `FilterBar` or anything else needs categorical colour, **do not invent a ramp inline**; raise it with me as its own decision.

**Verification.**

- `npm test` in both proof consumers.
- Verify at `1366x768` and `1024x600` with no horizontal scroll, and confirm `:focus-visible` is styled — an unstyled focus ring is the accessibility regression this layer is supposed to prevent.
- Confirm the migrated repos actually render from `tokens.css`: grep that their old bespoke custom properties are gone, not merely shadowed.
- `pre-commit run --files <changed>` in every touched repo; respect the 250-line file cap.

**Done means:** `~/utils/web_ui` exists with a committed `dist/`, tagged `web_ui-v0.1.0`; both proof consumers import it, with their local `RangeSlider`/`FilterBar`/token blocks deleted; tests pass in both; and everything is committed and pushed.

Context, if you want it: `~/utils/unified-design-system/nielsen-audit.md` has the full grid, the deferred clusters, and the Phase 1 record. Phase 1 (`~/utils/design_system`, Dart) is done — 7 exports, 100% coverage, six consumers — and is the pattern to imitate: `publish_to: none`, own lint config, own tests, own coverage gate enforced in CI, tag-pinned dep.
