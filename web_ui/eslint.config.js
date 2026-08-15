// Type-aware flat config for the shared component layer.
//
// A trimmed version of awesome-mcp-explorer's: typescript-eslint's
// *type-checked* strict + stylistic presets, so anything they flag is an error.
// The consumers layer unicorn/sonarjs/perfectionist on top; this package keeps
// to the presets its own devDependencies actually declare, because a config
// referencing plugins that are not installed is a lint script that cannot run.
import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  // eslint.config.js itself is not in tsconfig.lint.json, so type-aware
  // rules cannot run on it; linting the linter config buys nothing anyway.
  { ignores: ["dist", "coverage", "eslint.config.js"] },
  { linterOptions: { reportUnusedDisableDirectives: "error" } },

  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  ...tseslint.configs.stylisticTypeChecked,

  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parserOptions: {
        project: ["./tsconfig.lint.json"],
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // Every exported symbol here is consumed across a package boundary, so
      // an explicit return type is documentation, not ceremony.
      "@typescript-eslint/explicit-function-return-type": "error",
    },
  },

  {
    // Tests reach for non-null assertions on queries that cannot return null
    // in a passing test; asserting them again would only add noise.
    files: ["**/*.test.{ts,tsx}"],
    rules: { "@typescript-eslint/no-non-null-assertion": "off" },
  },
);
