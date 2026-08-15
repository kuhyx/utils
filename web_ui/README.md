# @kuhyx/web-ui

The shared token + component layer for kuhy's web apps — the web counterpart to
`~/utils/design_system` (Dart). Owns the frozen palette, the spacing/radius/type
scales, and the components that were each reimplemented in two or more repos.

Consumers import the tokens rather than transcribing the token table by hand.
Source of truth for the *values* is `~/utils/unified-design-system/tokens.md`;
this package is its executable form for the web.

## Install

```jsonc
// package.json — pnpm only, see "Why the &path: suffix" below.
"dependencies": {
  "@kuhyx/web-ui": "github:kuhyx/utils#web_ui-v0.3.0&path:/web_ui"
}
```

```ts
import "@kuhyx/web-ui/tokens.css";        // once, at the app entry point
import "@kuhyx/web-ui/range-slider.css";  // only if you use RangeSlider

import { RangeSlider, fuzzyMatch, quantileValue } from "@kuhyx/web-ui";
```

### Why the `&path:/web_ui` suffix

`utils` is a monorepo with no root `package.json`, and **npm cannot install from
a subdirectory of a git repo** — `github:user/repo#tag` clones the root, looks
for `package.json` there, and fails with `ENOENT` (verified against npm 11.16).
pnpm supports the subdirectory via `&path:/<dir>`, which is why both consumers
are pnpm. This is the only difference from the Dart (`git: {url, ref, path}`) and
Python (`#subdirectory=`) conventions the rest of `utils` follows.

### Why `dist/` is committed

Vite does not transpile dependencies, so shipping raw `.tsx` would force
per-repo bundler config on every consumer. The tag carries a prebuilt `dist/`
(ESM + `.d.ts`, JSX already compiled, `.ts` specifiers rewritten to `.js`), so
consumers stay at zero config. **`pnpm build` before tagging, always** — a tag
whose `dist/` is stale ships old code to every consumer with no error.

## What's here

| Export | Notes |
| --- | --- |
| `tokens.css` | The `:root` block: palette, spacing, radius, type, shadows, focus ring. Also sets `:focus-visible` globally. |
| `RangeSlider` | Dual-thumb slider over a value *distribution*, not a linear ramp. |
| `range-slider.css` | Its styling, entirely in tokens. |
| `quantile.ts` helpers | `nth`, `clamp01`, `quantileValue`, `valueQuantile`, `fractionFromPointer`. |
| `fuzzyMatch` | Case-insensitive subsequence match. |

### The categorical ramp

`--cat-1` … `--cat-6` are for charts, tags and category dots — N mutually
distinguishable colours with **no** inherent meaning. Never use them for
semantic state; `--success`/`--warning`/`--danger` own that.

They deliberately leave the warm wedge the rest of the palette sits in, because
hue separation is the whole point of a categorical scale. The values were chosen
by search under a ≥20 CIE ΔE floor across normal vision *and* deuteranopia,
protanopia and tritanopia, ≥3:1 contrast on **both** backgrounds, and a
monotonic lightness staircase so the ramp survives greyscale. Re-run the proof
with `python3 ~/utils/unified-design-system/scripts/ramp_check.py` — it exits
non-zero if an edit breaks any of it. A seventh hue is not available: the best
candidate reaches only ΔE 17.9. Group the tail into "other" instead.

`fractionFromPointer` is deliberately pure geometry: it makes the slider's
behaviour testable without layout, which jsdom does not implement.

### RangeSlider is keyboard-operable

Both donor copies were pointer-only. The design system requires that every
action be reachable with the keyboard alone, and a `role="slider"` that ignores
arrow keys is an ARIA role that lies — so the shared version adds:

| Key | Effect |
| --- | --- |
| `←` `↓` / `→` `↑` | Step one sample through the distribution |
| `PageDown` / `PageUp` | Step ten samples |
| `Home` / `End` | Jump to the distribution's bounds |

Pass `label` **and** `format` to get the built-in head (name + value readout);
omit them for a bare track when the caller draws its own chrome, as
dufs-cloud's `SizeRange`/`DurationRange` wrappers do.

## Development

```bash
pnpm install
pnpm test       # vitest
pnpm coverage   # 100% branches/functions/lines/statements, enforced
pnpm lint       # tsc --noEmit && eslint
pnpm build      # tsc -b + copy CSS into dist/
```

The 100% bar matches Phase 1's `design_system`: a shared layer two repos depend
on does not get to be the least-tested code in the tree.

## Releasing

```bash
pnpm test && pnpm build
git add web_ui && git commit -m "web_ui: <what changed>"
git tag web_ui-v<major>.<minor>.<patch> && git push origin main --tags
```

Then bump the tag in each consumer's `package.json` and re-run `pnpm install`.
