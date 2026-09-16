// Kept in its own module so fast.js can import it without pulling in
// base.js, whose plugin imports are what make a cold lint slow.

/** Directories no consumer wants linted; a consumer adds its own on top. */
export const DEFAULT_IGNORES = ["dist", "coverage", "node_modules", "build"];
