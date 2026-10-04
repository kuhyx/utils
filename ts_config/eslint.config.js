// The preset lints itself. Everything here is plain JS, so the type-aware
// layer is off by construction; the fixture is excluded because its whole
// job is to violate.
import { defineConfig } from "./eslint/index.js";

export default defineConfig({
  aliasOnly: false,
  ignores: ["test/fixture"],
  overrides: [
    {
      // fast.js IS a preset: its default export is the built config, so the
      // call at the top level is the module's whole purpose.
      files: ["eslint/fast.js"],
      rules: { "unicorn/no-top-level-side-effects": "off" },
    },
  ],
  tsconfigRootDir: import.meta.dirname,
});
