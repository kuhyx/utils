# `@kuhyx/ts-core`

Framework-free TypeScript utilities shared across kuhy's games and web apps.

Deliberately **no React and no CSS** — those live in
[`@kuhyx/web-ui`](../web_ui). A game that needs a seeded RNG should not have
to install a UI package to get one; that coupling is what makes people vendor
their own copy instead, which is how these ended up duplicated four ways.

## Install

**pnpm only.** npm cannot install a subdirectory of a git repo — it ignores
the `&path:` key, looks for `package.json` at the repo root and fails with
ENOENT. Every consumer of this package must be on pnpm.

```jsonc
// package.json
"dependencies": {
  "@kuhyx/ts-core": "github:kuhyx/utils#ts_core-v0.1.0&path:/ts_core"
}
```

## What it ships

| Export | Notes |
| --- | --- |
| `Clock`, `createRealClock`, `realClock`, `createManualClock`, `ManualClock` | Injectable time source, so real-time mechanics are driven by a scripted clock in tests instead of racing the wall clock. |
| `Rng`, `createRng`, `nextFloat`, `nextInt`, `nextChance`, `pick` | Seeded mulberry32, free-function style over mutable state. |
| `SeededRng`, `createSeededRng` | The same core, closure style. |

### Why the RNG has two interfaces

The repos that had grown their own copy did not agree on shape: konbini-67
used mutable state plus free functions (`nextFloat(rng)`); sims3-clone and
europe-county-map returned an object of closures (`rng.next()` / `rng.float()`).

Both ship here rather than being reconciled into one, because **the sequence
is the contract**. These repos have seeded tests and "same seed → identical
world" guarantees, so changing how many times a helper advances the generator
silently re-rolls every saved world. A shared package that did that would be
worse than the duplication it replaced.

The generator core is identical in both, so a given seed produces the same
float sequence whichever interface you use — asserted in the tests.

`int` is inclusive of both bounds, matching sims3-clone and europe-county-map.
konbini-67's local helper took a single *exclusive* max; it maps to
`nextInt(rng, 0, max - 1)`.

### The golden-sequence test

`rng.test.ts` pins the first five floats for seed `12345`, captured from the
**pre-extraction** konbini-67 implementation. If that test fails, the shared
core has stopped reproducing the sequence every consumer's saved seeds depend
on. Regenerating those constants to make a failure go away defeats the entire
point of the test — fix the code instead.

### `hotline3d` is deliberately not a consumer

`hotline3d/hotline-kernel/src/core/rng.ts` looks like the same generator but
uses `%` and `Math.trunc` where mulberry32 uses `>>>`/`>>`. Measured, it
produces a **different sequence** — so adopting this package would change its
generated output. Left alone on purpose.

## Commands

```bash
pnpm install
pnpm test        # vitest
pnpm coverage    # 100% branches/functions/lines/statements, enforced
pnpm lint        # tsc --noEmit + eslint (type-aware, strict)
pnpm build       # tsc -> dist/ (ESM + .d.ts), committed to the tag
```

`dist/` is committed, like `web_ui`'s: Vite does not transpile dependencies,
so a consumer would otherwise need per-repo bundler config. CI fails if the
committed `dist/` does not match a fresh build.
