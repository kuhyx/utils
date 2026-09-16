/**
 * Steps one thumb by `delta` positions through the distribution. Pure, so the
 * keyboard contract is testable without layout.
 *
 * Steps to the next *distinct* value rather than the next index. Real
 * distributions are lumpy -- awesome-mcp-explorer's star counts hold ~1500
 * duplicate zeros -- and an index step inside a run of equal values changes the
 * index while leaving the value (and therefore the thumb, and the filter)
 * exactly where it was. That reads as a dead arrow key.
 */
export declare function steppedValue(values: readonly number[], current: number, delta: number): number;
/**
 * The value a thumb at `current` moves to for a key, or `undefined` when the
 * key is not one the slider handles (so the event is left to the browser).
 * Arrow keys step one distinct value, Page keys ten, Home/End jump to the
 * bounds.
 */
export declare function keyTarget(key: string, values: readonly number[], current: number): number | undefined;
//# sourceMappingURL=stepped-value.d.ts.map