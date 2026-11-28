/// <reference types="vitest/config" />
import { getViteConfig } from "astro/config";

export default getViteConfig({
  test: {
    coverage: {
      exclude: ["src/index.ts", "src/test/**", "src/**/*.d.ts"],
      include: ["src/**/*.ts"],
      provider: "v8",
      // A shared layer that several repos depend on does not get to be the
      // least-tested code in the tree. `.astro` files are outside `include`:
      // the component is markup, covered by RangeSlider.astro.test.ts.
    },
    environment: "jsdom",
    globals: true,
    include: ["src/**/*.test.ts"],
    setupFiles: ["./src/test/setup.ts"],
  },
});
