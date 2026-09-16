// The type-aware baseline every kuhyx TypeScript repo lints against.
//
// typescript-eslint's *type-checked* strict + stylistic presets, so anything
// they flag is an error, not a warning. On top: unicorn (all), sonarjs
// (cognitive complexity / duplicate logic), perfectionist (sorting). Unused
// disable directives are themselves errors, so every `eslint-disable` in a
// consumer must be load-bearing.
//
// Split by concern so no file crosses the 250-line cap: this file wires the
// presets and the type-aware parser; overrides.js holds the house "off" list
// (each with its reason); naming.js and imports.js hold the rules the article
// calls "structural" -- filenames matching exports, imports only through
// aliases.
//
// Deliberately absent:
//   - eslint-plugin-react: 7.37.x still calls context.getFilename(), removed
//     in ESLint 10, so it crashes the run. @eslint-react covers the ground
//     (see the React layer).
//
// TypeScript stays on 6.0.x, not 7.x: typescript-eslint requires
// "typescript >=4.8.4 <6.1.0", and losing every type-aware rule would be a far
// bigger regression than gaining the Go-native compiler. The pin is
// allowlisted in utils/dependency-freshness.allowlist.yaml.
import js from "@eslint/js";
import perfectionist from "eslint-plugin-perfectionist";
import sonarjs from "eslint-plugin-sonarjs";
import unicorn from "eslint-plugin-unicorn";
import globals from "globals";
import tseslint from "typescript-eslint";

import { DEFAULT_IGNORES } from "./ignores.js";
import { imports } from "./imports.js";
import { naming } from "./naming.js";
import { overrides } from "./overrides.js";
import { requireNonEmptyString } from "./require.js";

/** Globs the type-aware rules apply to. */
export const TS_FILES = ["**/*.{ts,tsx,mts,cts}"];

export { DEFAULT_IGNORES } from "./ignores.js";

/**
 * The baseline config array.
 *
 * @param {object} options
 * @param {string} options.tsconfigRootDir Consumer's repo root
 *   (`import.meta.dirname` in its eslint.config.js). Required, because
 *   pre-commit runs ESLint from the Git root while control-panel and
 *   dufs-cloud keep their web app one level down -- cwd is not the root.
 * @param {string[]} [options.ignores] Extra ignore globs.
 * @param {boolean} [options.aliasOnly] Ban `../` parent-relative imports so
 *   every cross-directory import goes through the repo's `@/` alias. Default
 *   true; a repo with no alias configured turns it off with a reason.
 */
export function base({ aliasOnly = true, ignores = [], tsconfigRootDir }) {
  requireNonEmptyString(tsconfigRootDir, "base() tsconfigRootDir");
  return tseslint.config(
    { ignores: [...DEFAULT_IGNORES, ...ignores] },
    { linterOptions: { reportUnusedDisableDirectives: "error" } },

    js.configs.recommended,
    ...tseslint.configs.strictTypeChecked,
    ...tseslint.configs.stylisticTypeChecked,
    unicorn.configs.all,
    sonarjs.configs.recommended,
    perfectionist.configs["recommended-natural"],

    {
      files: TS_FILES,
      languageOptions: {
        parserOptions: { projectService: true, tsconfigRootDir },
      },
      rules: {
        // `type X = {}` and `interface X {}` are interchangeable for the
        // shapes this codebase writes; picking one keeps diffs quiet.
        "@typescript-eslint/consistent-type-definitions": ["error", "interface"],

        // Every exported symbol is read by someone who did not write it, so
        // an explicit boundary type is documentation, not ceremony.
        "@typescript-eslint/explicit-module-boundary-types": "error",

        // `any` and `!` are how a model hides a hole in its reasoning. Both
        // are already errors in strictTypeChecked; restating them here makes
        // the intent survive a preset upgrade that softens either.
        "@typescript-eslint/no-explicit-any": "error",
        "@typescript-eslint/no-non-null-assertion": "error",

        // Numbers in template literals are unambiguous and pervasive
        // (counts, totals, grades).
        "@typescript-eslint/restrict-template-expressions": [
          "error",
          { allowNumber: true },
        ],
      },
    },

    ...naming,
    ...(aliasOnly ? imports : []),
    ...overrides,

    // Plain JS config files get no type-aware linting, and they run under
    // Node (eslint.config.js, vitest.config.js, scripts) so its globals are
    // known rather than each `process` being an undefined variable.
    {
      extends: [tseslint.configs.disableTypeChecked],
      files: ["**/*.{js,mjs,cjs}"],
      languageOptions: { globals: globals.node },
    },
  );
}
