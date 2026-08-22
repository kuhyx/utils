/**
 * Small text helpers shared by the consumers' filter layers.
 *
 * Hand-rolled rather than pulling in Fuse.js, matching the house posture of no
 * runtime dependencies for things this small.
 */
/**
 * Case-insensitive subsequence match: every character of `query` appears in
 * `target`, in order, though not necessarily adjacently. An empty query matches
 * everything, so callers can pass the raw search box value straight through.
 *
 * dufs-cloud called this `fuzzyMatch` and awesome-mcp-explorer `matchesFuzzy`;
 * the implementations were identical apart from identifier names.
 */
export declare function fuzzyMatch(query: string, target: string): boolean;
//# sourceMappingURL=text.d.ts.map