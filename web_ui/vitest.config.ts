import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    coverage: {
      exclude: ["src/index.ts", "src/**/*.d.ts"],
      include: ["src/**/*.{ts,tsx}"],
      provider: "v8",
      // The same bar Phase 1's design_system holds: a shared layer that two
      // repos depend on does not get to be the least-tested code in the tree.
      thresholds: { branches: 100, functions: 100, lines: 100, statements: 100 },
    },
    environment: "jsdom",
    globals: true,
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["./src/test/setup.ts"],
  },
});
