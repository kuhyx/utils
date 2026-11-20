import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    coverage: {
      include: ["src/kuhy-credit.js"],
      provider: "v8",
      thresholds: { branches: 100, functions: 100, lines: 100, statements: 100 },
    },
    environment: "jsdom",
    include: ["src/**/*.test.js"],
  },
});
