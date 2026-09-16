// The shared preset, nothing else local except one frozen API name. This
// package is one of the repos the bar is defined for. Framework-free, so no
// React layer.
import { defineConfig } from "@kuhyx/ts-config";

export default defineConfig({
  // Flat files under src/, no layers to fence and no alias configured.
  aliasOnly: false,
  overrides: [
    {
      files: ["src/rng.ts"],
      rules: {
        // `nextChance` is public API consumed by three repos; the preset's
        // boolean-name prefixes would rename it to `isNextChance`, which is
        // worse prose and a breaking change for no safety gain.
        "unicorn/consistent-boolean-name": "off",
      },
    },
  ],
  // tsconfig.json excludes the tests so they never land in dist/; the lint
  // project widens the include for type-aware rules (see tsconfig.lint.json).
  project: ["./tsconfig.lint.json"],
  tsconfigRootDir: import.meta.dirname,
});
