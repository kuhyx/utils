// One deliberate violation per rule family in test/fixture, and the rule id
// that must catch it. A rule missing from this table is a rule the preset
// does not prove; a fixture file missing from it is a plant nobody checks.
export const EXPECTED = {
  "e2e/home.spec.ts": [
    "playwright/missing-playwright-await",
    "playwright/no-conditional-in-test",
  ],
  "src/components/button.tsx": [
    "jsx-a11y/alt-text",
    "jsx-a11y/click-events-have-key-events",
    "react-hooks/set-state-in-effect",
    "react-you-might-not-need-an-effect/no-derived-state",
  ],
  "src/design-system/theme.ts": ["boundaries/dependencies"],
  "src/helper.test.ts": ["vitest/expect-expect", "vitest/no-focused-tests"],
  "src/pages/home.tsx": ["boundaries/dependencies"],
  "src/router/routes.ts": ["boundaries/dependencies"],
  "src/services/api.ts": [
    "@typescript-eslint/no-explicit-any",
    "@typescript-eslint/no-non-null-assertion",
    "boundaries/dependencies",
    "no-restricted-imports",
  ],
  "src/Wrong_Name.ts": ["unicorn/filename-case"],
};

/** Files that must lint clean: proves the presets do not fire on good code. */
export const CLEAN = ["src/components/item-list.tsx", "src/mocks/user.ts", "src/utils/helper.ts"];
