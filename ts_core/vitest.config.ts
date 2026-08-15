import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    coverage: {
      exclude: ["src/index.ts", "src/**/*.d.ts"],
      include: ["src/**/*.ts"],
      provider: "v8",
      // Same bar as design_system and web_ui: a shared layer several repos
      // depend on does not get to be the least-tested code in the tree.
      thresholds: { branches: 100, functions: 100, lines: 100, statements: 100 },
    },
    // No jsdom: this package is framework-free. `performance.now()` exists in
    // plain node, which is the only browser-ish API it touches.
    environment: "node",
    globals: true,
    include: ["src/**/*.test.ts"],
  },
});
