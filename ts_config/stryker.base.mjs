// Mutation testing base. Stryker flips `<` to `<=`, empties arrays, inverts
// conditions and swaps return values; a test that still passes was not
// testing behaviour.
//
// No `break` threshold on purpose -- the article's one hard rule: treat the
// score as a detector, never as a KPI. The weekly workflow reports it; nothing
// fails on it.
/** @type {import("@stryker-mutator/api/core").PartialStrykerOptions} */
export const strykerBase = {
  coverageAnalysis: "perTest",
  ignoreStatic: true,
  incremental: true,
  mutate: ["src/**/*.ts", "src/**/*.tsx", "!src/**/*.test.*", "!src/**/*.spec.*", "!src/**/*.d.ts"],
  reporters: ["clear-text", "progress", "json", "html"],
  testRunner: "vitest",
  thresholds: { break: null, high: 80, low: 60 },
  timeoutMS: 60_000,
};
