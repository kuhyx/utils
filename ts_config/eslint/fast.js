// The editor-hook subset: the rules that catch the model's most common holes
// without type information and without loading the heavy plugins.
//
// Used by the Claude Code PostToolUse hook that reports (never fixes) lint
// findings on the file just edited, against a 1.0 s per-turn budget. The
// full type-aware bar stays in pre-commit; this is the same-session feedback
// the article calls "put the rules in front of the model".
//
// Measured cold on one fixture file (2026-09-16, this machine): bare
// typescript-eslint 0.50 s; +unicorn 0.87 s; +sonarjs 0.75 s; all of
// base() without types 1.28 s. Importing a plugin is the cost, not the
// number of its rules that run, so this file loads none of the three -- nor
// base.js, which imports them (that alone was +0.55 s).
import js from "@eslint/js";
import tseslint from "typescript-eslint";

import { DEFAULT_IGNORES } from "./ignores.js";
import { imports } from "./imports.js";

export default tseslint.config(
  { ignores: DEFAULT_IGNORES },
  js.configs.recommended,
  ...tseslint.configs.strict,
  ...tseslint.configs.stylistic,
  {
    rules: {
      "@typescript-eslint/consistent-type-definitions": ["error", "interface"],
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-non-null-assertion": "error",
    },
  },
  ...imports,
);
