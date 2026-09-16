// End-to-end specs. No kuhyx repo had Playwright on 2026-09-16; the preset
// ships so the first one that does gets the same bar without inventing it.
//
// The rules that matter most for model-written e2e: a conditional inside a
// test (the test passes whichever branch runs), a forgotten `await` on an
// async matcher (the assertion never fires), and `.only`.
import playwright from "eslint-plugin-playwright";

/** @type {import("eslint").Linter.Config[]} */
export const playwrightConfig = [
  {
    ...playwright.configs["flat/recommended"],
    files: ["**/e2e/**", "**/*.e2e.{ts,js}", "**/*.pw.{ts,js}"],
    rules: {
      ...playwright.configs["flat/recommended"].rules,
      "playwright/missing-playwright-await": "error",
      "playwright/no-conditional-in-test": "error",
      "playwright/no-focused-test": "error",
      "playwright/no-skipped-test": "error",
    },
  },
];
