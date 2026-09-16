// Test files: the rules that catch a test which cannot fail, plus the
// relaxations that stop the strict presets fighting mocks and fixtures.
//
// `expect-expect` is the article's "tests with no assertions" -- a model
// writes `it("works", () => { render(<X/>) })` and it passes forever.
// `no-focused-tests` is the forgotten `.only` that silently skips the suite.
import vitest from "@vitest/eslint-plugin";

/** Globs vitest rules apply to. */
export const TEST_FILES = [
  "**/*.test.{ts,tsx,js,jsx}",
  "**/*.spec.{ts,tsx,js,jsx}",
  "**/test/**",
  "**/__tests__/**",
  "**/__fixtures__/**",
];

const RULES = {
  ...vitest.configs.recommended.rules,
  "vitest/expect-expect": "error",
  "vitest/no-disabled-tests": "error",
  "vitest/no-focused-tests": "error",
  // vitest's `expect(value, message)` is how a loop of assertions names the
  // case that failed; the rule's default of one argument would ban it.
  "vitest/valid-expect": ["error", { maxArgs: 2 }],
};

/** @type {import("eslint").Linter.Config[]} */
export const vitestConfig = [
  {
    files: TEST_FILES,
    plugins: { vitest },
    rules: RULES,
  },
  // `typecheck` makes valid-title & co. read the TS type of a test's
  // arguments; it needs parser services, which only the TS files have.
  {
    files: ["**/*.{ts,tsx,mts,cts}"],
    settings: { vitest: { typecheck: true } },
  },
  {
    files: TEST_FILES,
    rules: {
      "@typescript-eslint/no-empty-function": "off",
      // Tests reach for `!` on queries that cannot return null in a passing
      // test; asserting them again would only add noise.
      "@typescript-eslint/no-non-null-assertion": "off",
      "@typescript-eslint/require-await": "off",
      "@typescript-eslint/unbound-method": "off",
      "sonarjs/no-duplicate-string": "off",
      // Test helpers live beside the tests that use them; hoisting every
      // fixture factory to module scope to satisfy a scoping rule would
      // scatter each test's setup away from the test.
      "unicorn/consistent-function-scoping": "off",
      // A no-op stub is the point of a stub.
      "unicorn/no-empty-file": "off",
    },
  },
];
