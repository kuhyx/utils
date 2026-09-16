import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    coverage: {
      include: ["eslint/**/*.js", "stryker.base.mjs"],
      provider: "v8",
      // The same bar as ts_core and web_ui: the package every repo's lint
      // runs through does not get to be the least-tested code in the tree.
      thresholds: { branches: 100, functions: 100, lines: 100, statements: 100 },
    },
    environment: "node",
    include: ["test/**/*.test.js"],
    testTimeout: 120_000,
  },
});
