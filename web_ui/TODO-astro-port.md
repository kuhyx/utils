# Port @kuhyx/web-ui from React to Astro + vanilla TS

## what
kuhy chose one framework for every web UI: Astro, with no React islands. This
package is the first blocker. `RangeSlider` is its only React export. It
becomes `RangeSlider.astro` plus a `<range-slider>` custom element. The
pure-TS helpers and the CSS stay as they are. Every repo's
`TODO-astro-migration.md` waits for the tag this produces.

## steps
1. Keep these as they are: `quantile.ts` (`nth`, `clamp01`, `quantileValue`,
   `valueQuantile`, `fractionFromPointer`), `stepped-value.ts` (`keyTarget`,
   `steppedValue`), `text.ts` (`fuzzyMatch`), `tokens.css`, `range-slider.css`.
2. Write `src/range-slider-element.ts`, a `RangeSliderElement extends HTMLElement`
   registered as `range-slider`. Inputs: a `values` property (number[]), `lo` and
   `hi` attributes, a `label` attribute, and a `format` property (a function).
   Output: a bubbling `change` CustomEvent with `{ lo, hi }`. Keep the current
   DOM: two `<button role="slider">` thumbs with `aria-valuemin`, `aria-valuemax`
   and `aria-valuenow`, grab-the-nearer-thumb on pointer, and the keyboard map in
   README.md. All of the logic stays in the existing pure helpers.
3. Write `src/RangeSlider.astro`. It server-renders the same markup (track,
   thumbs, optional head) inside `<range-slider>`. Its `<script>` imports the
   element module, so including the component registers the element.
4. Order: element and its tests first, then the `.astro` wrapper, then exports
   and packaging, then README, then the tag.
5. Packaging. tsc cannot emit `.astro`, so ship the `.astro` source as it is.
   Astro compiles `.astro` files from dependencies. Add to `exports`:
   `"./RangeSlider.astro": "./src/RangeSlider.astro"` and
   `"./range-slider": "./dist/range-slider-element.js"`. Add `src/*.astro`
   to `files`. Keep `dist/` committed for the `.ts` output. The `.astro`
   script imports `../dist/range-slider-element.js`, never the `.ts` source.
6. Consumers import it like this:
   `import RangeSlider from "@kuhyx/web-ui/RangeSlider.astro";` in frontmatter.
   Scripts use `import "@kuhyx/web-ui/range-slider";` and listen for `change`.
   Tokens stay `import "@kuhyx/web-ui/tokens.css";` in the shared layout.
7. Dependencies, all exact pins via pnpm: drop `peerDependencies.react`,
   `react`, `react-dom`, `@types/react`, `@types/react-dom` and
   `@testing-library/react`. Add `astro@7.4.4` as a devDependency (for the
   Container API and `astro check`), `@astrojs/check@0.9.12` and
   `@testing-library/dom` at its newest stable. Add
   `peerDependencies.astro: ">=7.4.0"`.
8. Tests. `range-slider.test.tsx` becomes `range-slider-element.test.ts`, which
   covers the custom element in jsdom: pointer, keyboard, the `change` event and
   the ARIA attributes. Add `RangeSlider.astro.test.ts`, which uses
   `experimental_AstroContainer` to check the server markup. Keep coverage at
   100% for `src/**/*.ts`. Exclude `.astro` from coverage, since its script
   holds only the import.
9. Rewrite README.md's Install and "What's here" sections for the Astro API.
   Then tag `web_ui-v0.5.0`. Before tagging, run `pnpm build`.

## done
Run from `~/src/utils/web_ui`:
`pnpm install --frozen-lockfile && pnpm lint && pnpm coverage && pnpm build && ! grep -q '"react"' package.json && ! find src -name '*.tsx' | grep -q . && git tag -l web_ui-v0.5.0 | grep -q .`
This exits 0.

## verify
Do it in the first consumer migrated, awesome-mcp-explorer, because it uses
`RangeSlider`. Check that the slider drags and that arrow keys and Home/End
step. Use a headless chromium at 4K and at a mobile viewport. The filter must
update and there must be no console errors.

## read first
- `~/src/utils/web_ui/README.md`: keyboard map, why `&path:/web_ui`, release steps.
- `~/src/utils/web_ui/src/range-slider.tsx` and `range-slider.test.tsx`.
- The consumers and their tags:
  - control-panel/web: v0.3.2
  - signal-bot/web: v0.3.1
  - dufs-cloud/web: v0.3.1
  - awesome-mcp-explorer: v0.3.1
  - foss-audit: v0.4.0
- Astro docs: "Publish to NPM" (shipping `.astro`), and `reference/container-reference`.

REMOVE ME AFTER FINISH
