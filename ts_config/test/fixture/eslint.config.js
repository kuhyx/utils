import { defineConfig, folderElements } from "../../eslint/index.js";

export default defineConfig({
  boundaries: {
    elements: folderElements([
      "components", "services", "utils", "pages", "router", "mocks", "design-system",
    ]),
  },
  // The fixture reaches its preset by relative path; a consumer imports the
  // package name, so the alias-only rule never sees this line there.
  ignores: ["eslint.config.js"],
  playwright: true,
  react: true,
  tsconfigRootDir: import.meta.dirname,
});
