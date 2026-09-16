// The preset lints itself. Everything here is plain JS, so the type-aware
// layer is off by construction; the fixture is excluded because its whole
// job is to violate.
import { defineConfig } from "./eslint/index.js";

export default defineConfig({
  aliasOnly: false,
  ignores: ["test/fixture"],
  tsconfigRootDir: import.meta.dirname,
});
