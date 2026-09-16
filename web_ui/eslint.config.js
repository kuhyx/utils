// The shared preset with the React layer, plus one frozen API name. This
// package is one of the repos the bar is defined for.
import { defineConfig } from "@kuhyx/ts-config";

export default defineConfig({
  // Flat files under src/, no layers to fence and no alias configured.
  aliasOnly: false,
  overrides: [
    {
      files: ["src/text.ts"],
      rules: {
        // `fuzzyMatch` is public API at four call sites in dufs-cloud and
        // awesome-mcp-explorer; the preset's prefix list would rename it to
        // `matchesFuzzy`, a breaking change for no safety gain. Revisit at
        // the next major.
        "unicorn/consistent-boolean-name": "off",
      },
    },
  ],
  // tsconfig.json excludes the tests so they never land in dist/; the lint
  // project widens the include for type-aware rules (see tsconfig.lint.json).
  project: ["./tsconfig.lint.json"],
  react: true,
  tsconfigRootDir: import.meta.dirname,
});
