# `@kuhyx/ts-config`

The one lint / TypeScript bar every kuhyx TypeScript repo extends. Plain JS
and JSON, no build step: a git tag is the release.

Born 2026-09-16 from Evil Martians' *Ten anti-AI-slop moves for frontend
projects*: every rule here is a deterministic gate that decides with an exit
code what a reviewer would otherwise have to notice in a model-written diff.
Before this package the ten repos carried hand-copied `eslint.config.js`
files in three different strictness tiers.

## Install

**pnpm only** (npm cannot install a subdirectory of a git repo).

```jsonc
// package.json
"devDependencies": {
  "@kuhyx/ts-config": "github:kuhyx/utils#ts_config-v0.1.0&path:/ts_config",
  "eslint": "10.10.0",
  "typescript": "6.0.3",
  "typescript-eslint": "8.70.0"
}
```

The three peers are the consumer's; every plugin is a `dependency` of this
package so a consumer never lists one. Bump every consumer to the same
`typescript-eslint` -- two copies in one resolution tree are two plugin
instances, and flat config rejects the second.

## Use

```jsonc
// tsconfig.json
{ "extends": "@kuhyx/ts-config/tsconfig", "compilerOptions": { "lib": ["ES2023", "DOM"], "jsx": "react-jsx", "paths": { "@/*": ["./src/*"] } } }
```

```js
// eslint.config.js
import { defineConfig, folderElements } from "@kuhyx/ts-config";

export default defineConfig({
  tsconfigRootDir: import.meta.dirname,
  react: true,
  boundaries: { elements: folderElements(["components", "services", "utils", "types"]) },
  // Repo-specific overrides go last and each carries the reason it exists.
  overrides: [],
});
```

`knip.json`: `{ "extends": "@kuhyx/ts-config/knip" }`. `.jscpd.json`: copy
`jscpd.base.json` (jscpd has no extends). `stryker.config.mjs`:
`import { strykerBase } from "@kuhyx/ts-config/stryker"; export default { ...strykerBase };`

## What is in it

| Export | Content |
| --- | --- |
| `./tsconfig` | `strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes` and the rest of the strictness block. No output options. |
| `defineConfig()` | `base` + optional `react` / `vitest` (default on) / `playwright` / `boundaries` + `overrides`. |
| `base()` | typescript-eslint strict+stylistic *type-checked*, unicorn (all), sonarjs, perfectionist; `no-explicit-any`, `no-non-null-assertion`, `explicit-module-boundary-types`; kebab-case filenames; alias-only imports (`aliasOnly: false` to drop); the house "off" list, each with its reason (`overrides.js`). |
| `react` | react-hooks, @eslint-react (type-checked), react-refresh, jsx-a11y strict, react-you-might-not-need-an-effect. |
| `vitestConfig` | `expect-expect`, `no-focused-tests`, `no-disabled-tests`, `valid-expect` + the test-file relaxations. |
| `playwrightConfig` | conditionals in tests, missing `await`, `.only`. |
| `boundaries()` | eslint-plugin-boundaries with the article's default policies (components→services→utils; router→pages; design-system isolated; mocks test-only). `folderElements([...])` builds the element list for a `src/<layer>/` tree; `allow: { layer: [...] }` overrides one layer. |
| `./eslint/fast` | Type-free subset for the editor hook: 0.52 s cold on one file (base without types: 1.28 s). Report-only use. |
| `./knip`, `./jscpd`, `./stryker` | Dead code, duplicate code, mutation testing bases. Stryker has **no** `break` threshold on purpose: a detector, not a KPI. |

## What the tests prove

`test/fixture/` is a mini repo with one planted violation per rule family
(`any`, `!`, `.only`, a test with no assertion, a parent-relative import,
services→components, router→utils, design-system→services, a page importing
a mock, a derived-state effect, an `img` without `alt`, a conditional in an
e2e test, a `Wrong_Name.ts`). `test/expected.js` names the rule that must
catch each; the suite runs the real CLI over the fixture and fails if a plant
is missed or a clean file is flagged. `pnpm coverage` holds the factories at
100% branches.

## Known limits

- `eslint-plugin-jsx-a11y` 6.10.2 declares peer ESLint ≤ 9. It runs cleanly
  under 10 (the fixture proves `alt-text` and `click-events-have-key-events`);
  if a release starts crashing, the React layer is where it comes out.
- `eslint-plugin-react` is deliberately absent (calls `context.getFilename()`,
  removed in ESLint 10). @eslint-react covers it.
- TypeScript stays on 6.0.x: typescript-eslint caps at `<6.1.0`. Allowlisted
  in `../dependency-freshness.allowlist.yaml`.
