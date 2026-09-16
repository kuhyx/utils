// Layer boundaries: the dependency direction is declared, and the linter
// enforces it.
//
// A model keeps no architectural context between sessions and drifts toward
// the "GitHub average" -- a service that imports a component because that was
// the shortest path. This is the fence. Elements are per repo (they name real
// directories); the default policy set is the article's:
//
//   components -> services, utils, types, design-system
//   services   -> utils, types
//   utils / types / config -> types only (no domain logic underneath)
//   design-system -> design-system, types (isolated from state, API, domain)
//   router     -> pages only
//   mocks      -> importable from tests only
//
// Anything not listed is disallowed, so an element type with no policy can
// import nothing outside itself -- adding a type means writing its policy.
import boundariesPlugin from "eslint-plugin-boundaries";

import { requireNonEmptyArray, requireNonEmptyString } from "./require.js";

/** The article's default policies, keyed by element type. */
export const DEFAULT_ALLOW = {
  components: ["services", "utils", "types", "design-system", "components"],
  config: ["types"],
  "design-system": ["design-system", "types"],
  mocks: ["types", "mocks"],
  pages: ["components", "services", "utils", "types", "design-system", "pages"],
  router: ["pages"],
  services: ["utils", "types", "services"],
  types: ["types"],
  utils: ["utils", "types"],
};

/**
 * Element descriptors for a conventional `src/<type>/` layout.
 *
 * v7 elements are folders: the pattern names the directory itself and every
 * file below it belongs to that element. (`src/<type>/*` would make each
 * *sub*-folder its own element and leave the files directly inside unknown.)
 *
 * @param {string[]} types Directory names under `src/` that are layers.
 * @param {string} [root] Path prefix the directories live under.
 */
export function folderElements(types, root = "src") {
  return types.map((type) => ({ pattern: `${root}/${type}`, type }));
}

/**
 * @param {object} options
 * @param {string} options.tsconfigRootDir Consumer repo root, so the TS
 *   resolver finds the `@/` alias in the consumer's tsconfig.
 * @param {Array<{type: string, pattern: string}>} options.elements
 *   The repo's layers; `folderElements([...])` builds the common case.
 * @param {Record<string, string[]>} [options.allow] Per-type allow lists.
 *   Merged over DEFAULT_ALLOW, so a repo overrides one layer, not all.
 * @param {string[]} [options.testFiles] Globs that may import mocks.
 */
export function boundaries({
  allow = {},
  elements,
  testFiles = ["**/*.test.*", "**/*.spec.*", "**/test/**"],
  tsconfigRootDir,
}) {
  requireNonEmptyArray(elements, "boundaries() elements");
  requireNonEmptyString(tsconfigRootDir, "boundaries() tsconfigRootDir");
  const merged = { ...DEFAULT_ALLOW, ...allow };
  const known = new Set(elements.map((element) => element.type));
  const policies = Object.entries(merged)
    .filter(([from]) => known.has(from))
    .map(([from, to]) => {
      const anyOf = to.filter((type) => known.has(type));
      return { allow: { to: { element: { types: { anyOf } } } }, from: { element: { type: from } } };
    });
  return [
    {
      files: ["**/*.{ts,tsx,js,jsx,mts,cts}"],
      plugins: { boundaries: boundariesPlugin },
      rules: {
        "boundaries/dependencies": [
          "error",
          {
            default: "disallow",
            policies: [
              ...policies,
              // Tests may reach any layer, mocks included. Mocks appear in no
              // production allow list, so a non-test module importing one is
              // either dead code or a fixture leaking into the build.
              {
                allow: { to: { element: { types: { anyOf: [...known] } } } },
                from: { file: { categories: "test" } },
              },
            ],
          },
        ],
      },
      settings: {
        // Element patterns are matched relative to root-path, which defaults
        // to process.cwd(). pre-commit runs from the Git root and the tests
        // from the package dir, so the repo root is passed explicitly or the
        // patterns match nothing and every file is "unknown".
        "boundaries/elements": elements,
        "boundaries/files": [{ category: "test", pattern: testFiles }],
        "boundaries/root-path": tsconfigRootDir,
        "import/resolver": {
          typescript: { alwaysTryTypes: true, project: tsconfigRootDir },
        },
      },
    },
  ];
}
