import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    coverage: {
      include: ["src/kuhy-credit.js"],
      provider: "v8",
    },
    environment: "jsdom",
    include: ["src/**/*.test.js"],
  },
});
